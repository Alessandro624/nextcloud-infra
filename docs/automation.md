# Backup automation and Telegram

Requires Python 3.10+, Docker access and configured [backup storage](backup.md). Install rclone for cloud copies. Run one service per AIO installation.

Prepare this configuration, configure optional [monitoring](monitoring.md), then start the service. Finish with [network](network.md) and [security](security.md) checks.

## Configure

1. Complete an initial successful AIO backup. Set `config/backup.json` to that exact volume/path and an external destination; see [backup](backup.md). Use a dedicated external directory. The service checks the Borg mount matches the selected source.
2. Disable AIO's daily schedule and other backup jobs. Do not run AIO backup/restore/update operations or the manual export helper alongside this service.
3. Copy `config/automation.example.json` to `config/automation.json` and review the defaults:

   | Setting | Default |
   | --- | --- |
   | Daily backup | 02:00, Europe/Rome |
   | Completed export retention | Last 2 managed generations, locally and externally |
   | Minimum free export space | 10 GiB; increase for your repository size |
   | Manual quota, shared by all users | 1 per rolling 24 hours; 3 per rolling 7 days |
   | Manual cooldown / scheduled reservation | 6 hours |
   | Telegram | Disabled |

Starting after the scheduled time can trigger a backup immediately. The scheduler runs at most once per local date, including daylight-saving changes; busy jobs delay it. Failed backup/export stages are not rerun that day; completed cloud exports are retried separately.

Nextcloud stops during backup/export and restarts before the external upload. Automatic AIO updates stay disabled.

Borg retains backups from the last 7 days, plus 4 weekly and 6 monthly archives. Each export contains the full repository. Rotation removes only managed copies after a new copy verifies; allow space for a third export. Inspect failed, partial or untracked exports manually before cleanup; incomplete `.partial-*` directories are not resumed and must be inspected before manual cleanup. The free-space threshold does not estimate backup size.

## Enable Telegram

Create a bot with [@BotFather](https://t.me/BotFather), then:

1. Save the token in `credentials/telegram-token.secret` (one line), or set `TELEGRAM_BOT_TOKEN` in the service environment. Protect the file with permissions limited to the service account and administrators. Never commit it.
2. Set `telegram_enabled` to `true`. Enter numeric `telegram_user_ids` and `telegram_chat_ids` in the local JSON. Both allowlists are required and checked on every message and callback. Obtain IDs from Telegram's `getUpdates` response using a local API client; do not post the token in a URL or chat.
3. Open the bot in Telegram and press Start. For a group, add the bot and use that group's chat ID plus the permitted human user IDs.
4. Use a dedicated bot without a webhook or another polling process. This service uses outbound HTTPS long polling.

| Command | Result |
| --- | --- |
| `/help` | Command list |
| `/status` | Nextcloud health and workflow phase |
| `/backup_status` | Last successful local backup and verified external copy recorded here |
| `/storage` | Free space on the export filesystem |
| `/backup` | Request a backup with a single-use confirmation valid for 60 seconds |

Manual limits are checked again at confirmation. A started attempt consumes quota even if it fails; rejected/expired requests do not. Pending scheduled backups take priority. Quotas and the operation lock survive restarts. There is no Telegram override, restore or delete command.

Telegram reports failures, recovery and manually requested backup completion. Scheduled successes are quiet. Telegram outages do not stop backups. Use [Healthchecks](monitoring.md) for service status and offline alerts.

## Start on Windows

Run from the repository using the account that owns Docker Desktop and the rclone configuration:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install tzdata
Copy-Item config/automation.example.json config/automation.json # Only on first setup
# Edit config/automation.json and config/backup.json before continuing.
./.venv/Scripts/python.exe scripts/automation.py check
```

`check` validates local settings without contacting services. After configuring monitoring, start with:

```powershell
./windows/automation.ps1
```

For persistent use, create a Task Scheduler task at logon under the same account: program `powershell.exe`, arguments `-NoProfile -File "ABSOLUTE_REPO_PATH\windows\automation.ps1"`. Select **Do not start a new instance**, disable the execution time limit and enable restart on failure. Docker Desktop must be available in that session. Keep the PC awake. The service has its own daily scheduler; do not create a second daily task.

## Start on Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install tzdata
cp config/automation.example.json config/automation.json # Only on first setup
# Edit both local JSON files.
.venv/bin/python scripts/automation.py check
```

After configuring monitoring, start with:

```bash
.venv/bin/python -u scripts/automation.py serve
```

If running the automation manually on a host where the persistent service uses `SERVICE_USER`, run it as that same account. Do not run the automation itself as `root`, because files created under `backup/automation` or `backup/exports` could later become inaccessible to the systemd service.

Explicitly select the absolute configuration path reported by `rclone config file` for the account that configured rclone:

```bash
sudo -u SERVICE_USER -H env \
  RCLONE_CONFIG=/absolute/path/rclone.conf \
  /absolute/path/nextcloud-infra/.venv/bin/python \
  /absolute/path/nextcloud-infra/scripts/automation.py serve
```

Use `sudo` for system administration such as systemd or ownership corrections, not to run the automation as `root`.

Run only one automation instance: use either the manual command or the service below.

For persistent use, install the template once, then edit it **before starting**:

```bash
sudo cp config/nextcloud-automation.service.example /etc/systemd/system/nextcloud-automation.service
sudoedit /etc/systemd/system/nextcloud-automation.service
```

Replace `SERVICE_USER` with an existing account (`id SERVICE_USER`) and every `/absolute/path/...` below with the real path. The template's `nextcloud-backup` account is not created automatically. Preserve the other service settings:

```ini
[Service]
User=SERVICE_USER
WorkingDirectory=/absolute/path/nextcloud-infra
ExecStart=/absolute/path/nextcloud-infra/.venv/bin/python -u /absolute/path/nextcloud-infra/scripts/automation.py serve
Environment="RCLONE_CONFIG=/absolute/path/rclone.conf"
```

Find the rclone path as the user who configured it. The service account needs access to the rclone configuration and credentials, Docker, and read/write access to the automation-managed `backup/automation` and `backup/exports` directories. The service also needs read access to completed exports retained for cloud retries. Verify before starting:

```bash
sudo -u SERVICE_USER -H /absolute/path/nextcloud-infra/.venv/bin/python --version
sudo -u SERVICE_USER -H docker ps
sudo -u SERVICE_USER -H rclone --config /absolute/path/rclone.conf listremotes
```

For an existing service, use `sudo systemctl edit nextcloud-automation` instead of copying the template again. When overriding `ExecStart`, put an empty `ExecStart=` line immediately before its replacement.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nextcloud-automation
journalctl -u nextcloud-automation -f
```

For an already running service, apply edits with `sudo systemctl restart nextcloud-automation` only when no backup is running.

### Linux permission errors

- `217/USER`: correct `User=` to an existing account; also replace the template's repository paths.
- Docker socket permission denied: if authorized, run `sudo usermod -aG docker SERVICE_USER`, verify with `sudo -u SERVICE_USER -H docker ps`, then restart the service. Docker group membership grants root-equivalent privileges. Reconnect interactive SSH sessions to refresh groups; do not change socket permissions.
- Permission errors under `backup/automation` or `backup/exports`: stop the service and any manual instance while idle. Inspect the affected paths, then correct ownership only in these managed directories:

```bash
id -gn SERVICE_USER # Use this value for SERVICE_GROUP.
sudo find /absolute/path/nextcloud-infra/backup/automation /absolute/path/nextcloud-infra/backup/exports \
  -maxdepth 2 -printf '%M %u:%g %p\n'
sudo chown -R SERVICE_USER:SERVICE_GROUP \
  /absolute/path/nextcloud-infra/backup/automation \
  /absolute/path/nextcloud-infra/backup/exports
sudo -u SERVICE_USER -H test -w /absolute/path/nextcloud-infra/backup/automation
sudo -u SERVICE_USER -H test -w /absolute/path/nextcloud-infra/backup/exports
sudo systemctl restart nextcloud-automation
journalctl -u nextcloud-automation -f
```

Keep state and lock files. Do not make them world-writable or recursively change the repository, Borg source or Docker volumes. Inspect `.partial-*` directories separately: they are incomplete exports, not automatically resumable archives.

## Verify and recover

Check a scheduled backup, Telegram authorization and manual limits, then restore an external copy using [validation](validation.md). Run the [monitoring tests](monitoring.md#acceptance-test) if enabled. Local unit tests (`python -m unittest discover -s tests`) simulate external services.

Stop the service before maintenance and let an active job finish.

Every five minutes, a separate worker retries interrupted application recovery after Borg and the export helper have stopped. It does not block the scheduler or heartbeat. Persistent ambiguity or unhealthy applications keep new backups blocked.

For `copy_type: rclone`, the completed export and destination are recorded before application restart. Failed upload, verification or retention is retried every five minutes after the previous attempt ends, including after a service restart. Retries reuse that export, recheck its checksum and remote content, preserve quotas and do not stop Nextcloud again. New backups wait until the pending copy succeeds; a prolonged outage therefore also delays new local backups. Monitor the dedicated backup check. Configuration changes, corrupt exports and permission errors require correction; retries cannot repair them. Local filesystem copies and incomplete exports are not automatically resumed.

Telegram polling and service heartbeats retry independently. Backup reporting events are best effort and are not persisted. A failed backup alone does not mark healthy applications as unhealthy.

If automatic recovery cannot proceed, inspect AIO, Borg and the export helper; finish or stop the interrupted operation, restart AIO applications and confirm their health. Then, with the service stopped, run recovery **as the same service account**, not as `root`:

```bash
sudo -u SERVICE_USER -H env \
  RCLONE_CONFIG=/absolute/path/rclone.conf \
  /absolute/path/nextcloud-infra/.venv/bin/python \
  /absolute/path/nextcloud-infra/scripts/automation.py recover
```

This checks that Borg/export are stopped and Nextcloud is healthy, then clears the interruption flag without resetting quotas. Inspect partial exports separately. Preserve `backup/automation/state.json`; deleting it loses quota and retention history. Use only one repository checkout/service per AIO installation. Do not migrate this state to a different installation without reviewing its recorded paths.

References: [AIO backup](https://github.com/nextcloud/all-in-one#backup), [AIO orchestration script](https://github.com/nextcloud/all-in-one/blob/main/Containers/mastercontainer/daily-backup.sh), [Telegram Bot API](https://core.telegram.org/bots/api).
