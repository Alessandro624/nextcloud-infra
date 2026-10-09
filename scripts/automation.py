"""Run the backup scheduler and optional Telegram control service on the Docker host."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import queue
import re
import shutil
import threading
import time
import urllib.request
import uuid
from zoneinfo import ZoneInfo

import backup
import monitoring

MASTER = "nextcloud-aio-mastercontainer"
BORG = "nextcloud-aio-borgbackup"
STATE_DIR = backup.ROOT / "backup/automation"
GENERATION = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")


def settings():
    path = backup.ROOT / "config/automation.json"
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    defaults = json.loads((backup.ROOT / "config/automation.example.json").read_text())
    if set(cfg) != set(defaults):
        raise ValueError("Use all and only the fields in automation.example.json")
    ZoneInfo(cfg["timezone"])
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cfg["backup_time"]):
        raise ValueError("backup_time must be HH:MM")
    for key in ("keep_exports", "minimum_free_gib", "manual_daily_limit", "manual_weekly_limit", "minimum_interval_hours"):
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError(key + " must be a positive integer")
    if type(cfg["telegram_enabled"]) is not bool:
        raise ValueError("telegram_enabled must be boolean")
    if not isinstance(cfg["telegram_token_file"], str) or not cfg["telegram_token_file"]:
        raise ValueError("telegram_token_file must be a path")
    for key in ("telegram_user_ids", "telegram_chat_ids"):
        if not isinstance(cfg[key], list) or any(type(i) is not int for i in cfg[key]):
            raise ValueError(key + " must contain numeric IDs")
        if cfg["telegram_enabled"] and not cfg[key]:
            raise ValueError(key + " cannot be empty when Telegram is enabled")
    return cfg


@contextmanager
def instance_lock(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "service.lock").open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def next_slot(cfg, now):
    zone = ZoneInfo(cfg["timezone"])
    local = datetime.fromtimestamp(now, zone)
    hour, minute = map(int, cfg["backup_time"].split(":"))
    slot = local.replace(hour=hour, minute=minute, second=0, microsecond=0, fold=0)
    if slot.timestamp() <= now:
        slot += timedelta(days=1)
    return slot.timestamp()


def manual_allowed(cfg, state, now, busy=False):
    if busy or state.get("active"):
        return False, "An operation is active or needs operator recovery."
    local = datetime.fromtimestamp(now, ZoneInfo(cfg["timezone"]))
    if local.strftime("%H:%M") >= cfg["backup_time"] and state.get("scheduled_day") != local.date().isoformat():
        return False, "Today's scheduled backup is pending. Retry after its cooldown."
    starts = state.get("starts", [])
    deadlines = [s["at"] + cfg["minimum_interval_hours"] * 3600 for s in starts]
    manual = sorted(s["at"] for s in starts if s["manual"])
    for window, limit in ((86400, cfg["manual_daily_limit"]), (604800, cfg["manual_weekly_limit"])):
        recent = [stamp for stamp in manual if stamp > now - window]
        if len(recent) >= limit:
            deadlines.append(recent[-limit] + window)
    retry = max(deadlines, default=0)
    if retry > now:
        return False, "Rate limit. Earliest retry: " + datetime.fromtimestamp(retry, ZoneInfo(cfg["timezone"])).isoformat()
    if next_slot(cfg, now) - now <= cfg["minimum_interval_hours"] * 3600:
        return False, "Reserved for the next scheduled backup. Retry after its cooldown."
    return True, "Allowed"


def inspect(name):
    return json.loads(backup.run(["docker", "inspect", "--format", "{{json .State}}", name], timeout=15))


def validate_source(data):
    mounts = json.loads(backup.run(["docker", "inspect", "--format", "{{json .Mounts}}", BORG]))
    expected_type = "volume" if data["source_type"] == "volume" else "bind"
    if not any(
        m["Destination"] == "/mnt/borgbackup" and m["Type"] == expected_type and m.get("Name" if expected_type == "volume" else "Source", "").rstrip("/") == data["source"].rstrip("/") for m in mounts
    ):
        raise ValueError("Configured source differs from the AIO Borg mount")


def aio(**flags):
    values = dict(DAILY_BACKUP="0", START_CONTAINERS="1", STOP_CONTAINERS="0", AUTOMATIC_UPDATES="0", CHECK_BACKUP="0")
    values.update(flags)
    command = ["docker", "exec"]
    for key, value in values.items():
        command += ["-e", key + "=" + value]
    backup.run(command + [MASTER, "/daily-backup.sh"])


class Service:
    def __init__(self, cfg, data, directory=STATE_DIR):
        self.cfg, self.data, self.directory = cfg, data, directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "state.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {"starts": [], "copies": [], "offset": 0}
        self.mutex = threading.RLock()
        self.busy = False
        self.pending = {}
        self.monitor = monitoring.Monitor.load(backup.ROOT)
        self.monitor_events = queue.Queue(maxsize=16)
        self.scheduler_tick = time.monotonic()
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if cfg["telegram_enabled"] and not self.token:
            token_file = Path(cfg["telegram_token_file"])
            if not token_file.is_absolute():
                token_file = backup.ROOT / token_file
            self.token = token_file.read_text(encoding="utf-8-sig").strip()
        if cfg["telegram_enabled"] and not self.token:
            raise ValueError("Set TELEGRAM_BOT_TOKEN in the service environment")

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def api(self, method, **payload):
        body = json.dumps(payload).encode()
        request = urllib.request.Request("https://api.telegram.org/bot" + self.token + "/" + method, data=body, headers={"Content-Type": "application/json"})
        try:
            with monitoring.http_client().open(request, timeout=40) as response:
                result = json.load(response)
            if not result.get("ok"):
                raise ValueError("Telegram rejected request")
            return result["result"]
        except Exception:
            # HTTP exceptions can include the token-bearing URL.
            raise RuntimeError("Telegram request failed; check connectivity and configuration") from None

    def notify(self, message):
        if self.cfg["telegram_enabled"]:
            for chat in self.cfg["telegram_chat_ids"]:
                try:
                    self.api("sendMessage", chat_id=chat, text=message)
                except RuntimeError:
                    print("Telegram notification failed", flush=True)

    def begin(self, manual, day=None):
        with self.mutex:
            now = time.time()
            if self.busy or self.state.get("active"):
                return "Operation active or interrupted; operator recovery required if the service restarted."
            if manual:
                allowed, reason = manual_allowed(self.cfg, self.state, now)
                if not allowed:
                    return reason
            if self.data["copy_type"] == "none":
                return "Configure an external copy destination first."
            self.state["starts"] = [s for s in self.state["starts"] if s["at"] > now - max(604800, self.cfg["minimum_interval_hours"] * 3600)]
            self.state["starts"].append({"at": now, "manual": manual})
            self.state["active"] = True
            self.state["active_since"] = now
            self.state["phase"] = "Starting"
            if day:
                self.state["scheduled_day"] = day
            self.save()  # Persist quota before any work starts.
            self.busy = True
            threading.Thread(target=self.work, args=(manual,), daemon=False).start()
            return "Backup started. Temporary Nextcloud downtime is expected."

    def phase(self, value):
        with self.mutex:
            self.state["phase"] = value
            self.save()

    def work(self, manual):
        needs_restart = False
        if not manual:
            self.report_backup("start")
        try:
            self.phase("Preflight")
            if not inspect(MASTER)["Running"]:
                raise ValueError("Master must already be running")
            previous = inspect(BORG)
            if previous["Running"]:
                raise ValueError("Borg operation already running")
            validate_source(self.data)
            base = Path(self.data["export_directory"])
            if not base.is_absolute():
                base = backup.ROOT / base
            base.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(base).free < self.cfg["minimum_free_gib"] * 1024**3:
                raise ValueError("Insufficient free export disk space")
            self.phase("AIO backup")
            needs_restart = True
            aio(DAILY_BACKUP="1", START_CONTAINERS="0")
            result = inspect(BORG)
            if result["Running"] or result["ExitCode"] != 0 or result["StartedAt"] == previous["StartedAt"]:
                raise ValueError("No fresh successful Borg backup")
            with self.mutex:
                self.state["last_backup"] = time.time()
                self.save()
            self.phase("Export")
            backup.run(["docker", "stop", MASTER])
            folder = backup.export(self.data)
            self.phase("Restart")
            self.restart()
            needs_restart = False
            self.phase("External copy")
            backup.copy(self.data, folder)
            with self.mutex:
                self.state["copies"].append({"name": folder.name, "base": str(base.resolve()), "type": self.data["copy_type"], "destination": self.data["copy_destination"]})
                self.state["last_copy"] = time.time()
                self.save()
            self.phase("Retention")
            self.prune()
            recovered = self.state.get("failed", False)
            with self.mutex:
                self.state["failed"] = False
                self.save()
            if manual or recovered:
                self.notify("Backup and external copy verified." + (" Service recovered after a previous failure." if recovered else ""))
            if not manual:
                self.report_backup("success")
        except Exception as error:
            # Keep diagnostics on the host, not in Telegram.
            detail = str(error) if isinstance(error, ValueError) else type(error).__name__
            print("Backup failed: " + detail, flush=True)
            with self.mutex:
                self.state["failed"] = True
                self.save()
            self.notify("Backup workflow failed during " + self.state.get("phase", "unknown phase") + ". Check the host logs and AIO.")
            if not manual:
                self.report_backup("fail")
        finally:
            restart_failed = False
            if needs_restart:
                try:
                    self.restart()
                except Exception:
                    restart_failed = True
                    self.notify("Nextcloud restart failed. Operator recovery required.")
            with self.mutex:
                self.state["active"] = restart_failed
                self.state["phase"] = "Recovery required" if restart_failed else "Idle"
                self.busy = False
                self.save()

    def status_report(self):
        with self.mutex:
            state = dict(self.state)
            active = bool(state.get("active"))
            busy = self.busy
            tick = self.scheduler_tick
        now = time.time()
        age = now - state.get("active_since", 0)
        maintenance = busy and active and 0 <= age <= self.monitor.cfg["maximum_workflow_seconds"] and state.get("phase") in {"AIO backup", "Export", "Restart"}
        result = {"observed_at": now, "last_backup": state.get("last_backup"), "last_copy": state.get("last_copy"),
                  "phase": state.get("phase", "Idle"), "workflow_active": active, "maintenance": maintenance,
                  "scheduler_alive": time.monotonic() - tick < 90, "error_code": "NONE"}
        for key, name in (("nextcloud", "nextcloud-aio-nextcloud"), ("apache", "nextcloud-aio-apache")):
            try:
                container = inspect(name)
                result[key] = container.get("Health", {}).get("Status", "unknown") if container["Running"] and not container.get("Restarting") else "stopped"
            except Exception:
                result[key] = "unknown"
        base = Path(self.data["export_directory"])
        if not base.is_absolute():
            base = backup.ROOT / base
        try:
            result["export_free_gib"] = shutil.disk_usage(base).free / 1024**3
            if result["export_free_gib"] < self.cfg["minimum_free_gib"]:
                result["error_code"] = "LOW_SPACE"
        except OSError:
            result["error_code"] = "STORAGE_UNAVAILABLE"
        if not maintenance and any(result[k] != "healthy" for k in ("nextcloud", "apache")):
            result["error_code"] = "SERVICE_UNHEALTHY"
        if state.get("failed"):
            result["error_code"] = "WORKFLOW_FAILED"
        if active and (age < 0 or age > self.monitor.cfg["maximum_workflow_seconds"]):
            result["error_code"] = "WORKFLOW_TIMEOUT"
        if active and not busy:
            result["error_code"] = "RECOVERY_REQUIRED"
        if not result["scheduler_alive"]:
            result["error_code"] = "SCHEDULER_STALLED"
        return monitoring.safe_payload(result)

    def report_backup(self, event):
        # Even a stalled DNS resolver must not delay backup or application recovery.
        if self.monitor.cfg["enabled"]:
            try:
                self.monitor_events.put_nowait(event)
            except queue.Full:
                print("Backup status queue full; event not delivered", flush=True)

    def deliver_backup_events(self):
        while True:
            event = self.monitor_events.get()
            try:
                self.monitor.ping("backup", event, self.status_report())
            except Exception:
                print("Backup status reporting failed", flush=True)
            finally:
                self.monitor_events.task_done()

    def heartbeat(self):
        while True:
            try:
                status = self.status_report()
                self.monitor.ping("service", "success" if status["error_code"] == "NONE" else "fail", status)
            except Exception:
                self.monitor.ping("service", "fail", {"error_code": "STATUS_UNAVAILABLE"})
            time.sleep(self.monitor.cfg["interval_seconds"])

    def restart(self):
        backup.run(["docker", "start", MASTER])
        aio()
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            states = [inspect(name) for name in ("nextcloud-aio-nextcloud", "nextcloud-aio-apache")]
            if all(s["Running"] and not s.get("Restarting") and s.get("Health", {}).get("Status") == "healthy" for s in states):
                return
            time.sleep(10)
        raise ValueError("Nextcloud health check timed out")

    def prune(self):
        # Only generations recorded by this service, for this destination and export root.
        base = Path(self.data["export_directory"])
        if not base.is_absolute():
            base = backup.ROOT / base
        base = base.resolve()
        copies = [c for c in self.state["copies"] if c["type"] == self.data["copy_type"] and c["destination"] == self.data["copy_destination"] and c["base"] == str(base)]
        for item in copies[: -self.cfg["keep_exports"]]:
            name = item["name"]
            if not GENERATION.fullmatch(name):
                raise ValueError("Invalid managed generation")
            if item["type"] == "rclone":
                remote = item["destination"].rstrip("/") + "/" + name
                backup.run(["rclone", "delete", remote, "--max-depth", "1", "--include", "/aio-backup.tar", "--include", "/aio-backup.tar.sha256", "--include", "/COPY-VERIFIED.txt"])
            else:
                self.remove_files(Path(item["destination"]), name)
            self.remove_files(base, name)
            with self.mutex:
                self.state["copies"].remove(item)
                self.save()

    @staticmethod
    def remove_files(base, name):
        base = base.resolve()
        folder = base / name
        if folder.is_symlink() or folder.resolve() != folder:
            raise ValueError("Unsafe retention path")
        for filename in ("aio-backup.tar", "aio-backup.tar.sha256", "COPY-VERIFIED.txt"):
            (folder / filename).unlink(missing_ok=True)
        if folder.exists():
            folder.rmdir()  # Never recursively delete unexpected content.

    def handle(self, update):
        callback = update.get("callback_query")
        msg = callback.get("message", {}) if callback else update.get("message", {})
        user = (callback or msg).get("from", {}).get("id")
        chat = msg.get("chat", {}).get("id")
        if user not in self.cfg["telegram_user_ids"] or chat not in self.cfg["telegram_chat_ids"]:
            return
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v[2] > now}
        if callback:
            entry = self.pending.get(callback.get("data"))
            text = "Confirmation expired or invalid."
            if entry and entry[:2] == (user, chat):
                del self.pending[callback["data"]]
                text = self.begin(True)
            self.api("answerCallbackQuery", callback_query_id=callback["id"], text="Request processed")
        else:
            if not 0 <= now - msg.get("date", 0) <= 60:
                return  # Do not execute commands queued while the bot was offline.
            command = msg.get("text", "").split("@", 1)[0].strip()
            if command == "/backup":
                with self.mutex:
                    allowed, text = manual_allowed(self.cfg, self.state, now, self.busy)
                if allowed:
                    key = uuid.uuid4().hex
                    self.pending[key] = (user, chat, now + 60)
                    self.api(
                        "sendMessage",
                        chat_id=chat,
                        text="Start backup? Nextcloud will be temporarily unavailable. Confirmation expires in 60 seconds.",
                        reply_markup={"inline_keyboard": [[{"text": "Confirm backup", "callback_data": key}]]},
                    )
                    return
            elif command == "/status":
                try:
                    running = inspect("nextcloud-aio-nextcloud")
                    text = "Nextcloud: " + ("healthy" if running.get("Health", {}).get("Status") == "healthy" and running["Running"] else "not healthy")
                except Exception:
                    text = "Nextcloud status unavailable"
                text += "\nWorkflow: " + self.state.get("phase", "Idle")
                if self.state.get("failed"):
                    text += "\nLast workflow failed; inspect host logs."
            elif command == "/backup_status":
                text = "\n".join(
                    key + ": " + (datetime.fromtimestamp(self.state[key], ZoneInfo(self.cfg["timezone"])).isoformat() if self.state.get(key) else "No recorded success")
                    for key in ("last_backup", "last_copy")
                )
            elif command == "/storage":
                base = Path(self.data["export_directory"])
                if not base.is_absolute():
                    base = backup.ROOT / base
                text = f"Export filesystem free: {shutil.disk_usage(base).free / 1024**3:.1f} GiB" if base.exists() else "Export directory not created yet."
            else:
                text = "/status /backup_status /storage /backup /help"
        self.api("sendMessage", chat_id=chat, text=text)

    def telegram(self):
        while True:
            try:
                updates = self.api("getUpdates", offset=self.state["offset"], timeout=25, allowed_updates=["message", "callback_query"])
                for update in updates:
                    with self.mutex:
                        self.state["offset"] = update["update_id"] + 1
                        self.save()  # Never replay a command after process failure.
                    self.handle(update)
            except Exception:
                print("Telegram polling failed; retrying", flush=True)
                time.sleep(10)

    def serve(self):
        if self.state.get("active"):
            self.notify("Interrupted workflow detected. Inspect AIO and recover on the host before clearing state.")
        if self.cfg["telegram_enabled"]:
            threading.Thread(target=self.telegram, daemon=True).start()
        if self.monitor.cfg["enabled"]:
            threading.Thread(target=self.deliver_backup_events, daemon=True).start()
            threading.Thread(target=self.heartbeat, daemon=True).start()
        while True:
            self.scheduler_tick = time.monotonic()
            now = datetime.now(ZoneInfo(self.cfg["timezone"]))
            day = now.date().isoformat()
            if now.strftime("%H:%M") >= self.cfg["backup_time"] and self.state.get("scheduled_day") != day:
                result = self.begin(False, day)
                if result.startswith("Backup started"):
                    print(result, flush=True)
            time.sleep(15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "serve", "recover"))
    args = parser.parse_args()
    cfg = settings()
    data = backup.config(backup.ROOT / "config/backup.json")
    if args.action == "check":
        monitoring.Monitor.load(backup.ROOT)
        if data["copy_type"] == "none":
            raise ValueError("Configure external storage before activation")
        print("Configuration valid; no services contacted")
        return
    with instance_lock(STATE_DIR):
        service = Service(cfg, data)
        if args.action == "recover":
            if inspect(BORG)["Running"] or not inspect(MASTER)["Running"]:
                raise ValueError("Stop Borg operations and restore the master before recovery")
            names = backup.run(["docker", "ps", "--format", "{{.Names}}"]).splitlines()
            if "nextcloud-infra-backup-export" in names:
                raise ValueError("Export helper still running")
            for name in ("nextcloud-aio-nextcloud", "nextcloud-aio-apache"):
                state = inspect(name)
                if not state["Running"] or state.get("Health", {}).get("Status") != "healthy":
                    raise ValueError("Restore Nextcloud health before recovery")
            service.state.update(active=False, phase="Idle")
            service.save()
            print("Recovery acknowledged; quota and copy history preserved")
        else:
            service.serve()


if __name__ == "__main__":
    main()
