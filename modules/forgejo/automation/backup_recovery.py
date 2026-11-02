"""Durable single-writer Forgejo restic workflow. Run through backup.sh/systemd."""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from zoneinfo import ZoneInfo

SOURCE = Path("/srv/forgejo")
STATE = Path("/var/lib/forgejo-backup")
MARKER = Path("/run/forgejo-backup-maintenance")


def sync_directory(path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    sync_directory(path.parent)


def run(command, timeout=14400):
    # A timed-out restic must not leave its rclone child writing concurrently.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
    except BaseException:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command)
    return output


class Workflow:
    def __init__(self, directory=STATE):
        self.directory = directory
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = directory / "pending.json"
        keys = ("LOCAL_REPO", "REMOTE_REPO", "RESTIC_PASSWORD_FILE", "RCLONE_CONFIG")
        self.config = {key: os.environ[key] for key in keys}
        if self.config["LOCAL_REPO"] != "/var/backups/forgejo/restic":
            raise ValueError("Review local repository path before changing this deployment")
        if not self.config["REMOTE_REPO"].startswith("rclone:"):
            raise ValueError("Expected the existing rclone restic destination")
        self.minimum = int(os.environ.get("MIN_FREE_GIB", "10"))
        if self.minimum < 1:
            raise ValueError("Invalid free space threshold")
        self.job = json.loads(self.path.read_text()) if self.path.exists() else None
        if self.job:
            if self.job.get("version") != 1 or self.job.get("config") != self.config:
                raise ValueError("Pending job configuration differs; operator review required")
            snapshot = self.job.get("snapshot")
            if snapshot is not None and not re.fullmatch(r"[0-9a-f]{64}", snapshot):
                raise ValueError("Invalid saved snapshot")
            if type(self.job.get("restart_needed")) is not bool:
                raise ValueError("Invalid recovery state")

    def save(self):
        write_json(self.path, self.job)

    def phase(self, value):
        self.job["phase"] = value
        self.save()
        print("Forgejo backup phase: " + value, flush=True)

    def dc(self, *args):
        return run(["docker", "compose", "--project-directory", str(SOURCE), "-f", str(SOURCE / "compose.yml"), *args], timeout=180)

    def health(self):
        # Same endpoint as the existing Forgejo deployment guide.
        run(["curl", "--noproxy", "*", "-fsS", "--max-time", "5", "http://127.0.0.1:13000/api/healthz"], timeout=10)

    def restore_app(self):
        if not self.job["restart_needed"]:
            return
        self.phase("Restart")
        self.dc("start", "forgejo")
        deadline = time.monotonic() + 300
        while True:
            try:
                self.health()
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise ValueError("Forgejo health did not recover")
                time.sleep(5)
        self.job["restart_needed"] = False
        self.save()
        MARKER.unlink(missing_ok=True)

    def restic(self, repo, *args):
        return run(["restic", "-r", repo, *args])

    def notify(self, event):
        try:
            run(["python3", str(SOURCE / "scripts/notify.py"), "backup", event], timeout=12)
        except Exception:
            print("Backup monitoring delivery failed", flush=True)

    def execute(self):
        local, remote = self.config["LOCAL_REPO"], self.config["REMOTE_REPO"]
        if self.job is None:
            self.job = {"version": 1, "config": self.config, "snapshot": None, "restart_needed": False,
                        "created": time.time(), "phase": "Preflight", "full_check": datetime.now(ZoneInfo("Europe/Rome")).isoweekday() == 7}
            self.save()
            self.notify("start")
        try:
            # After power loss restore service before any network-dependent work.
            self.restore_app()
            if self.job["snapshot"] is None:
                self.phase("Preflight")
                self.health()
                for path in (SOURCE, Path(local).parent):
                    if shutil.disk_usage(path).free < self.minimum * 1024**3:
                        raise ValueError("Insufficient local free space")
                if not (Path(local) / "config").is_file():
                    raise ValueError("Local restic repository missing")
                self.restic(local, "unlock")  # Stale locks only; never --remove-all.
                self.job["restart_needed"] = True
                self.phase("Local snapshot")  # Durable intent before stopping Forgejo.
                MARKER.write_text(str(int(time.time())))
                self.dc("stop", "-t", "120", "forgejo")
                container = self.dc("ps", "-aq", "forgejo").strip()
                if not container or run(["docker", "inspect", "--format", "{{.State.Running}}", container], timeout=15).strip() != "false":
                    raise ValueError("Forgejo is not stopped")
                output = self.restic(local, "backup", str(SOURCE), "--host", "forgejo", "--tag", "forgejo", "--json")
                # Only exit code zero reaches here; partial snapshots are never promoted.
                summaries = [json.loads(line) for line in output.splitlines() if line.strip()]
                ids = [item.get("snapshot_id") for item in summaries if item.get("message_type") == "summary"]
                if len(ids) != 1 or not isinstance(ids[0], str) or not re.fullmatch(r"[0-9a-f]{8,64}", ids[0]):
                    raise ValueError("No successful snapshot identifier")
                if run(["docker", "inspect", "--format", "{{.State.Running}}", container], timeout=15).strip() != "false":
                    raise ValueError("Forgejo was restarted during snapshot creation")
                snapshots = json.loads(self.restic(local, "snapshots", "--json", ids[0]))
                if len(snapshots) != 1 or not re.fullmatch(r"[0-9a-f]{64}", snapshots[0]["id"]):
                    raise ValueError("Snapshot identity is ambiguous")
                self.job["snapshot"] = snapshots[0]["id"]
                self.save()
                self.restore_app()
            # These steps are safe to repeat for this exact persisted snapshot.
            self.phase("Local verification")
            self.restic(local, "unlock")
            self.restic(local, "check")
            self.phase("External copy")
            self.restic(remote, "unlock")
            self.restic(remote, "copy", "--from-repo", local, "--from-password-file", self.config["RESTIC_PASSWORD_FILE"], self.job["snapshot"])
            self.phase("External verification")
            self.restic(remote, "check")
            if self.job["full_check"]:
                self.restic(local, "check", "--read-data")
                self.restic(remote, "check", "--read-data")
            self.phase("Retention")
            for repo in (remote, local):
                self.restic(repo, "forget", "--host", "forgejo", "--tag", "forgejo", "--keep-within", "7d", "--keep-weekly", "4", "--keep-monthly", "6", "--prune")
            write_json(self.directory / "last-success.json", {"at": time.time(), "snapshot": self.job["snapshot"]})
            self.path.unlink()
            sync_directory(self.directory)
            self.notify("success")
            print("Forgejo local/off-site backup and retention completed", flush=True)
        except Exception:
            try:
                self.restore_app()
            finally:
                self.notify("fail")
            raise


def main():
    import fcntl
    os.umask(0o077)
    with open("/run/lock/forgejo-backup.lock", "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        Workflow().execute()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Restic errors remain in the local journal; no exception or secret URL in alerts.
        print("Forgejo workflow failed: " + type(error).__name__, flush=True)
        raise SystemExit(1)
