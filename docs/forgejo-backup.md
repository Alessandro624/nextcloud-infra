# Forgejo backup and monitoring

After [setup](forgejo-setup.md), use the same root Bash session with `REPO_DIR` pointing to the trusted checkout. Fixed reference paths and ports are listed in [the module README](../modules/forgejo/README.md).

## Encrypted local and off-site backups

This is a **separate restic backup**, not Nextcloud AIO/Borg. It captures SQLite while Forgejo is stopped, along with repositories, LFS, packages, artifacts, secrets, config and scripts. Use a dedicated external prefix; never point these commands at a Nextcloud backup repository.

Use `/var/backups/forgejo` as a local directory outside `/srv/forgejo`, which is the backup source. No separate mount is required. A copy on the same disk does not protect against disk failure: verify the off-site copy and test restoration. If you later use a separate mounted disk, add a mount check to both backup and monitoring before relying on it.

```bash
install -d -m 700 /var/backups/forgejo/restic
install -d -m 700 /etc/forgejo-backup
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('/etc/forgejo-backup/restic.secret')
with p.open('x') as f:
    f.write(secrets.token_urlsafe(48) + '\n')
p.chmod(0o600)
PY
```

**Save the restic password in the password manager now.** Losing it makes all backup copies unusable. Do not rely on recovering it from the encrypted repository itself. Keep a recovery kit containing this document, the restic password, storage-account recovery access, rclone configuration, and Healthchecks setup.

Configure a MEGA remote named `forgejo-offsite` in the explicit service configuration below; enable `use_https = true` in its advanced settings. You may reuse the Nextcloud storage account, but keep the dedicated `forgejo-restic` directory separate. The root-run Forgejo service uses this file, not your interactive user's default rclone configuration. Other supported providers can use the same remote name.

```bash
rclone --config /etc/forgejo-backup/rclone.conf config
chmod 600 /etc/forgejo-backup/rclone.conf
# Confirm the remote exists; do not dump its credentials.
rclone --config /etc/forgejo-backup/rclone.conf listremotes
```

Create `/etc/forgejo-backup/environment` and replace the remote if needed:

```bash
install -m 600 "$REPO_DIR/modules/forgejo/automation/environment.example" /etc/forgejo-backup/environment
chmod 600 /etc/forgejo-backup/environment
# Review the remote prefix and minimum free space before initialization.
${EDITOR:-nano} /etc/forgejo-backup/environment
set -a
source /etc/forgejo-backup/environment
set +a
restic -r "$LOCAL_REPO" init
restic -r "$REMOTE_REPO" init --from-repo "$LOCAL_REPO" \
  --from-password-file "$RESTIC_PASSWORD_FILE" --copy-chunker-params
```

Run initialization once, against new dedicated repositories. Restic encrypts content and metadata before upload and deduplicates snapshots. Retention here is **7 days, 4 weekly, 6 monthly snapshots in each repository**, not two full exports. Do not `rclone sync` or manually delete restic repository files.

For MEGA, test unattended authentication and a full off-site restore. Budget shared account capacity for both services and temporary retention/prune space. Rclone normally moves deleted MEGA objects to the trash: review trash usage separately so retention actually frees capacity; do not purge unrelated account data. See [rclone MEGA settings](https://rclone.org/mega/).

Both repositories use the same password in this guide. The online host can delete its own backups: if protection from a compromised administrator/server is required, add a separately administered immutable/offline copy. A normal Drive folder alone does not provide that guarantee.

## External health notifications

Create two new Healthchecks checks, distinct from Nextcloud:

- **Forgejo backup:** daily at `03:30 Europe/Rome`, grace initially 2 hours, adjusted to measured runtime. Move this slot if the Nextcloud job can overlap and saturate disk/network.
- **Forgejo service:** 5-minute interval plus 5-minute grace. Configure recipients in Healthchecks so alerts work if this host is offline.

The sender accepts only HTTPS UUID URLs on `hc-ping.com`; it posts fixed status fields, not logs, credentials or repository names. Self-hosted Healthchecks requires an intentional change to the exact hostname validation.

```bash
python3 - <<'PY'
from pathlib import Path
from getpass import getpass
import json
p = Path('/etc/forgejo-backup/healthchecks.secret')
with p.open('x') as f:
    json.dump({'backup': getpass('Backup base ping URL: ').strip(),
               'service': getpass('Service base ping URL: ').strip()}, f)
p.chmod(0o600)
PY
install -m 700 "$REPO_DIR/modules/forgejo/scripts/notify.py" /srv/forgejo/scripts/notify.py
chmod 700 /srv/forgejo/scripts/notify.py
```

The shell wrappers below use a process deadline as well as the HTTP timeout, so DNS failure cannot indefinitely delay recovery. Missing pings are the fallback alert. Sending a ping is an outbound connection; no callback listener is installed.

## Install the recovery workflow

The shipped workflow includes persistent recovery from its first installation. Keep files root-owned. Do not run other restic writers against these dedicated repositories.

```bash
install -d -m 700 /var/lib/forgejo-backup
install -m 700 "$REPO_DIR/modules/forgejo/automation/backup.sh" /srv/forgejo/scripts/backup.sh
install -m 700 "$REPO_DIR/modules/forgejo/automation/backup_recovery.py" /srv/forgejo/scripts/backup_recovery.py
install -m 644 "$REPO_DIR"/modules/forgejo/systemd/forgejo-backup* /srv/forgejo/systemd/
install -m 644 /srv/forgejo/systemd/forgejo-backup* /etc/systemd/system/
bash -n /srv/forgejo/scripts/backup.sh
python3 -m py_compile /srv/forgejo/scripts/backup_recovery.py
systemd-analyze verify /etc/systemd/system/forgejo-backup.service /etc/systemd/system/forgejo-backup-recovery.service /etc/systemd/system/forgejo-backup-recovery.timer
systemctl daemon-reload
systemctl start --no-block forgejo-backup.service
journalctl -u forgejo-backup.service -f
```

Leave the log view with Ctrl+C (the job continues). Require successful verification, `/var/lib/forgejo-backup/last-success.json`, no `pending.json`, and healthy Forgejo. Then enable both timers:

```bash
systemctl enable --now forgejo-backup.timer forgejo-backup-recovery.timer
systemctl list-timers 'forgejo-backup*' --no-pager
```

The daily slot is 03:30 Europe/Rome. Adjust the installed timer (and its saved copy), Healthchecks schedule and optional bot configuration together, then run `systemctl daemon-reload` and restart the timer. Retention is fixed at 7 days, 4 weekly and 6 monthly snapshots; full verification runs on Sundays in Europe/Rome. Changing the verification timezone requires updating `automation/backup_recovery.py` too. See [recovery behavior and failure tests](forgejo-recovery.md).

## Service monitoring

Optional: install the separate [Forgejo Telegram bot](forgejo-telegram.md). Its token, service and files are independent of Nextcloud. Keep Healthchecks for external outage alerts.

This health check tests the local application endpoint and free space. Planned backup downtime is allowed for at most 2 hours; an old marker is failure. It does not prove that a client can log in over Tailscale, so also perform the external access test in [acceptance checks](forgejo-restore.md#acceptance).

```bash
install -m 700 "$REPO_DIR/modules/forgejo/scripts/health.sh" /srv/forgejo/scripts/health.sh
chmod 700 /srv/forgejo/scripts/health.sh
install -m 644 "$REPO_DIR/modules/forgejo/systemd/forgejo-health.service" /srv/forgejo/systemd/forgejo-health.service
install -m 644 "$REPO_DIR/modules/forgejo/systemd/forgejo-health.timer" /srv/forgejo/systemd/forgejo-health.timer
install -m 644 /srv/forgejo/systemd/forgejo-health.* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now forgejo-health.timer
systemctl start forgejo-health.service
```

The new unit files are included by the next backup. Rotate system logs, restrict journal access and never enable verbose HTTP/rclone logging around credentials. Healthchecks failure should leave backups and application recovery functional.
