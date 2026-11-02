"""Standalone Forgejo Telegram bot. Python standard library; Linux/systemd host."""

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.request
import uuid
from zoneinfo import ZoneInfo

UNIT = "forgejo-backup.service"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Redirect refused")


def client():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def settings(path, discover=False):
    cfg = json.loads(Path(path).read_text())
    expected = {
        "token_file",
        "user_ids",
        "chat_ids",
        "http_port",
        "timezone",
        "scheduled_time",
        "manual_daily_limit",
        "manual_weekly_limit",
        "minimum_interval_hours",
        "poll_seconds",
        "backup_enabled",
    }
    if set(cfg) != expected:
        raise ValueError("Use the fields from config.example.json")
    ZoneInfo(cfg["timezone"])
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cfg["scheduled_time"]):
        raise ValueError("Invalid scheduled_time")
    for key in ("user_ids", "chat_ids"):
        if not isinstance(cfg[key], list) or any(type(x) is not int for x in cfg[key]) or (not cfg[key] and not discover):
            raise ValueError("Both numeric allowlists are required")
    for key, low, high in (("http_port", 1, 65535), ("poll_seconds", 60, 3600), ("manual_daily_limit", 1, 10), ("manual_weekly_limit", 1, 30), ("minimum_interval_hours", 1, 24)):
        if type(cfg[key]) is not int or not low <= cfg[key] <= high:
            raise ValueError("Invalid " + key)
    if type(cfg["backup_enabled"]) is not bool or not isinstance(cfg["token_file"], str) or not Path(cfg["token_file"]).is_absolute():
        raise ValueError("Invalid backup_enabled or token_file")
    return cfg


def unit_status():
    try:
        fields = "LoadState,ActiveState,SubState,Result,ExecMainStatus,ExecMainStartTimestampMonotonic,ExecMainExitTimestampMonotonic"
        output = subprocess.run(["/usr/bin/systemctl", "show", UNIT, "--no-pager", "--property=" + fields], capture_output=True, text=True, check=True, timeout=10).stdout
        data = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        if data.get("LoadState") != "loaded":
            return "unavailable", 0
        start = int(data.get("ExecMainStartTimestampMonotonic", 0)) / 1e6
        end = int(data.get("ExecMainExitTimestampMonotonic", 0)) / 1e6
        if data.get("SubState") == "auto-restart":
            return "retrying", start
        if data.get("ActiveState") in {"activating", "active", "deactivating"}:
            return ("running" if start > 0 and 0 <= time.monotonic() - start <= 7200 else "overdue"), start
        if data.get("ActiveState") == "failed" or data.get("Result") not in (None, "success"):
            return "failed", start
        if not end:
            return "unknown", start
        return ("success" if data.get("ExecMainStatus") == "0" else "failed"), start
    except Exception:
        return "unavailable", 0


def allowed(cfg, state, now, result, last_start):
    if not cfg["backup_enabled"]:
        return False, "Manual backups are disabled."
    if result not in {"success", "failed", "unknown"}:
        return False, "Backup active, overdue or status unavailable."
    starts = state.get("starts", [])
    # A backwards clock must not reset quotas.
    if now < max(starts, default=0):
        return False, "Clock moved backwards; inspect the host."
    for window, limit in ((86400, cfg["manual_daily_limit"]), (604800, cfg["manual_weekly_limit"])):
        if sum(stamp > now - window for stamp in starts) >= limit:
            return False, "Manual backup quota reached."
    cooldown = cfg["minimum_interval_hours"] * 3600
    if (starts and now - max(starts) < cooldown) or (last_start > 0 and time.monotonic() - last_start < cooldown):
        return False, "Backup cooldown is active."
    local = datetime.fromtimestamp(now, ZoneInfo(cfg["timezone"]))
    hour, minute = map(int, cfg["scheduled_time"].split(":"))
    slot = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if any(abs((slot + timedelta(days=d)).timestamp() - now) <= cooldown for d in (-1, 0, 1)):
        return False, "Time reserved for scheduled backup."
    return True, "Allowed"


class Bot:
    def __init__(self, cfg, directory):
        self.cfg = cfg
        self.token = Path(cfg["token_file"]).read_text().strip()
        if not self.token:
            raise ValueError("Empty bot token")
        self.path = directory / "state.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {"offset": 0, "starts": [], "alerts": {}}
        self.lock = threading.RLock()
        self.pending = {}

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w") as stream:
            json.dump(self.state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)
        if os.name == "posix":
            fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def api(self, method, **payload):
        request = urllib.request.Request("https://api.telegram.org/bot" + self.token + "/" + method, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with client().open(request, timeout=35) as response:
                data = json.load(response)
            if not data.get("ok"):
                raise ValueError()
            return data["result"]
        except Exception:
            raise RuntimeError("Telegram request failed") from None

    def status(self):
        result, _ = unit_status()
        health = "unavailable"
        try:
            with client().open(f'http://127.0.0.1:{self.cfg["http_port"]}/api/healthz', timeout=5) as response:
                if response.status == 200 and json.loads(response.read(16384)).get("status") == "pass":
                    health = "healthy"
        except Exception:
            pass
        if health != "healthy" and result == "running":
            health = "maintenance"
        return {"service": health, "backup": result}

    def start_backup(self):
        with self.lock:
            result, stamp = unit_status()
            now = time.time()
            ok, reason = allowed(self.cfg, self.state, now, result, stamp)
            if not ok:
                return reason
            self.state["starts"] = [x for x in self.state["starts"] if x > now - 604800] + [now]
            self.save()  # Persist quota before requesting work; never replay uncertain requests.
        try:
            subprocess.run(["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", UNIT], capture_output=True, check=True, timeout=15)
            return "Backup requested. Temporary Forgejo downtime is expected; check /backup_status."
        except Exception:
            return "Request outcome uncertain or rejected. Check the host; quota remains consumed."

    def handle(self, update):
        callback = update.get("callback_query")
        msg = callback.get("message", {}) if callback else update.get("message", {})
        user = (callback or msg).get("from", {}).get("id")
        chat = msg.get("chat", {}).get("id")
        if user not in self.cfg["user_ids"] or chat not in self.cfg["chat_ids"]:
            return
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v[2] > now}
        if callback:
            key = callback.get("data", "")
            entry = self.pending.get(key)
            text = "Confirmation invalid or expired."
            if entry and entry[:2] == (user, chat):
                del self.pending[key]
                text = self.start_backup()
            self.api("answerCallbackQuery", callback_query_id=callback["id"], text="Request processed")
        else:
            if not 0 <= now - msg.get("date", 0) <= 60:
                return
            command = msg.get("text", "").split("@", 1)[0].strip()
            if command == "/backup":
                with self.lock:
                    result, stamp = unit_status()
                    ok, text = allowed(self.cfg, self.state, now, result, stamp)
                if ok:
                    key = uuid.uuid4().hex
                    self.pending[key] = (user, chat, now + 60)
                    self.api(
                        "sendMessage",
                        chat_id=chat,
                        text="Start Forgejo backup? Temporary downtime. Confirm within 60 seconds.",
                        reply_markup={"inline_keyboard": [[{"text": "Confirm backup", "callback_data": key}]]},
                    )
                    return
            elif command == "/status":
                text = "\n".join("Forgejo " + k + ": " + v for k, v in self.status().items())
            elif command == "/backup_status":
                text = "Forgejo backup unit: " + unit_status()[0] + ". Systemd result; not an independent archive verification."
            else:
                text = "/status /backup_status /backup /help"
        self.api("sendMessage", chat_id=chat, text=text)

    def poll_alerts(self):
        for key, value in self.status().items():
            if value in {"running", "maintenance"}:
                continue
            for chat in self.cfg["chat_ids"]:
                identity = str(chat) + ":" + key
                with self.lock:
                    previous = self.state["alerts"].get(identity)
                if previous != value and (previous is not None or value not in {"healthy", "success"}):
                    try:
                        self.api("sendMessage", chat_id=chat, text=f"Forgejo {key}: {value}.")
                    except RuntimeError:
                        continue
                with self.lock:
                    self.state["alerts"][identity] = value
                    self.save()

    def alerts(self):
        while True:
            try:
                self.poll_alerts()
            except Exception:
                print("Status monitoring failed; retrying", flush=True)
            time.sleep(self.cfg["poll_seconds"])

    def serve(self):
        threading.Thread(target=self.alerts, daemon=True).start()
        while True:
            try:
                for update in self.api("getUpdates", offset=self.state["offset"], timeout=20, allowed_updates=["message", "callback_query"]):
                    with self.lock:
                        self.state["offset"] = update["update_id"] + 1
                        self.save()
                    self.handle(update)
            except Exception:
                print("Bot polling failed; retrying in 10 seconds", flush=True)
                time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "discover", "serve"))
    parser.add_argument("--config", default="/etc/forgejo-bot/config.json")
    parser.add_argument("--state", type=Path, default=Path("/var/lib/forgejo-bot"))
    args = parser.parse_args()
    cfg = settings(args.config, discover=args.action == "discover")
    if args.action == "check":
        print("Configuration valid; no services contacted")
        return
    os.umask(0o077)
    args.state.mkdir(parents=True, exist_ok=True)
    import fcntl

    with (args.state / "service.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        bot = Bot(cfg, args.state)
        if args.action == "discover":
            for update in bot.api("getUpdates", timeout=0, allowed_updates=["message"]):
                msg = update.get("message", {})
                print("user_id:", msg.get("from", {}).get("id"), "chat_id:", msg.get("chat", {}).get("id"))
        else:
            bot.serve()


if __name__ == "__main__":
    main()
