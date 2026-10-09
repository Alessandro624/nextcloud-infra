"""Prepare AIO storage, export a stopped Borg repository, and copy verified exports."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    "source_type": "volume", "source": "nextcloud_aio_backupdir",
    "export_directory": "backup/exports", "copy_type": "none", "copy_destination": "",
}
IMAGE = "ghcr.io/nextcloud-releases/aio-borgbackup:latest"


def run(args, timeout=None):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE, timeout=timeout).stdout.strip()


def config(path):
    data = dict(DEFAULTS)
    if path.exists():
        supplied = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(supplied, dict) or set(supplied) - set(DEFAULTS):
            raise ValueError("Unknown configuration fields or invalid JSON object")
        data.update(supplied)
    if any(not isinstance(v, str) for v in data.values()):
        raise ValueError("All settings must be strings")
    if data["source_type"] not in ("volume", "path"):
        raise ValueError("source_type must be volume or path")
    source = data["source"]
    if data["source_type"] == "volume":
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]+", source):
            raise ValueError("Invalid Docker volume name")
    elif not source.startswith("/") or source == "/" or any(x in source for x in (",", "\n", "\r")):
        raise ValueError("Path source must be an absolute Docker-host Linux directory, not /")
    if not data["export_directory"]:
        raise ValueError("export_directory is required")
    if data["copy_type"] not in ("none", "local", "rclone"):
        raise ValueError("copy_type must be none, local or rclone")
    dest = data["copy_destination"]
    if data["copy_type"] != "none" and not dest:
        raise ValueError("copy_destination is required")
    if data["copy_type"] == "local" and not Path(dest).is_absolute():
        raise ValueError("Local copy_destination must be absolute")
    if data["copy_type"] == "rclone" and (not re.match(r"^[a-zA-Z0-9_-]+:.+", dest) or "://" in dest):
        raise ValueError("Use a configured rclone remote:path, without credentials")
    return data


def prepare(data):
    if data["source_type"] == "volume":
        run(["docker", "volume", "create", data["source"]])
    else:
        print("Create this directory on the Docker host and make it accessible to AIO.")
    print("Select this backup destination in AIO: " + data["source"])
    print("This does not configure AIO, move existing backups or run a backup.")


def stopped():
    # Inspect only the exact AIO container names, not other Docker projects.
    names = run(["docker", "ps", "-a", "--format", "{{.Names}}"] ).splitlines()
    for name in ("nextcloud-aio-mastercontainer", "nextcloud-aio-borgbackup"):
        if name not in names:
            raise ValueError(f"{name} is missing; export requires an initialized AIO backup")
        state = json.loads(run(["docker", "inspect", "--format", "{{json .State}}", name]))
        if state.get("Running") or state.get("Restarting"):
            raise ValueError(f"Stop {name} before export; no services were stopped automatically")
        if name.endswith("borgbackup") and state.get("ExitCode") != 0:
            raise ValueError("Last Borg operation failed; resolve it in AIO before exporting")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify(folder):
    folder = Path(folder).resolve()
    for name in ("aio-backup.tar", "aio-backup.tar.sha256"):
        path = folder / name
        if path.is_symlink() or path.resolve().parent != folder or not path.is_file():
            raise ValueError("Archive and checksum must be regular files inside the export")
    expected = (folder / "aio-backup.tar.sha256").read_text().strip().split()
    if len(expected) != 2 or expected[1] != "aio-backup.tar" or not re.fullmatch(r"[0-9a-f]{64}", expected[0]):
        raise ValueError("Invalid checksum file")
    if digest(folder / "aio-backup.tar") != expected[0]:
        raise ValueError("Archive SHA-256 mismatch")
    return folder


def export(data):
    stopped()
    if data["source_type"] == "volume":
        run(["docker", "volume", "inspect", data["source"]])  # Never create an empty source.
    base = Path(data["export_directory"])
    if not base.is_absolute():
        base = ROOT / base
    base = base.resolve()
    if "," in str(base):
        raise ValueError("Export directory must not contain commas (Docker mount syntax)")
    if data["source_type"] == "path":
        source = data["source"]
        if os.name == "nt":
            source = re.sub(r"^/(?:run/desktop/mnt/host|host_mnt)/([a-zA-Z])/(.*)$", r"\1:/\2", source)
        source_path = Path(source).resolve()
        if base == source_path or source_path in base.parents:
            raise ValueError("Export directory must be outside the backup source")
    base.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    partial = base / (".partial-" + name)
    partial.mkdir()
    source_mount = f"type={'volume' if data['source_type'] == 'volume' else 'bind'},source={data['source']},target=/backup,readonly"
    # A fixed helper name prevents two exports on the same Docker daemon.
    # AIO must remain stopped; no external Borg writer may run during this command.
    command = "set -eu; test -f /backup/borg/config; test -d /backup/borg/data; test ! -e /backup/borg/aio-lockfile; test ! -e /backup/borg/lock.exclusive; test ! -e /backup/borg/lock.roster; tar -cf /export/aio-backup.tar -C /backup .; tar -tf /export/aio-backup.tar >/dev/null"
    run(["docker", "run", "--rm", "--name", "nextcloud-infra-backup-export", "--network", "none",
         "--mount", source_mount, "--mount", f"type=bind,source={partial},target=/export",
         "--entrypoint", "/bin/sh", IMAGE, "-c", command])
    stopped()  # Fail if an operator restarted AIO while exporting.
    archive = partial / "aio-backup.tar"
    (partial / "aio-backup.tar.sha256").write_text(digest(archive) + "  aio-backup.tar\n")
    verify(partial)
    final = base / name
    partial.rename(final)
    print("Verified export: " + str(final))
    return final


def copy(data, folder):
    folder = verify(folder)
    if folder.name.startswith(".partial-"):
        raise ValueError("Refusing an incomplete export")
    if {p.name for p in folder.iterdir()} != {"aio-backup.tar", "aio-backup.tar.sha256"}:
        raise ValueError("Export contains unexpected files; only archive and checksum may be copied")
    mode = data["copy_type"]
    if mode == "none":
        raise ValueError("External copy is disabled; set copy_type and copy_destination")
    if mode == "local":
        destination = Path(data["copy_destination"]).resolve()
        if not destination.is_dir():
            raise ValueError("Destination must already exist; check the disk/NAS is mounted")
        if destination == folder or folder in destination.parents:
            raise ValueError("Destination must be outside the export directory")
        final = destination / folder.name
        if final.exists():
            raise ValueError("Destination generation already exists; no overwrite performed")
        partial = destination / (".partial-" + folder.name)
        shutil.copytree(folder, partial)
        verify(partial)
        partial.rename(final)
    else:
        final = data["copy_destination"].rstrip("/") + "/" + folder.name
        run(["rclone", "copy", str(folder), final, "--immutable"])
        run(["rclone", "check", str(folder), final, "--download", "--one-way"])
        # Only this marker signifies a successful remote verification.
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "COPY-VERIFIED.txt"
            marker.write_text("Archive transfer verified by rclone check --download.\n")
            run(["rclone", "copyto", str(marker), final + "/COPY-VERIFIED.txt", "--immutable"])
    print("External copy verified: " + str(final))
    print("Transfer verification is not a Borg integrity check or a restore test.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "export", "copy", "verify"))
    parser.add_argument("--config", type=Path, default=ROOT / "config/backup.json")
    parser.add_argument("--export", type=Path, dest="folder", help="Completed export directory for copy/verify")
    args = parser.parse_args()
    if args.action in ("copy", "verify") and not args.folder:
        parser.error("--export is required")
    if args.action == "verify":
        print("SHA-256 verified: " + str(verify(args.folder)))
        return
    if not args.config.exists() and args.config != ROOT / "config/backup.json":
        raise ValueError("Configuration file does not exist")
    data = config(args.config)
    if args.action == "prepare":
        prepare(data)
    elif args.action == "export":
        export(data)
    else:
        copy(data, args.folder)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("Backup operation failed: " + str(error), file=sys.stderr)
        sys.exit(1)
