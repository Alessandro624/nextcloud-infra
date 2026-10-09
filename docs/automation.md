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

Starting after the scheduled time can trigger a backup immediately. The scheduler runs at most once per local date, including daylight-saving changes; busy jobs delay it, and failed daily jobs are not retried that day.

Nextcloud stops during backup/export and restarts before the external upload. Automatic AIO updates stay disabled.

Borg retains backups from the last 7 days, plus 4 weekly and 6 monthly archives. Each export contains the full repository. Rotation removes only managed copies after a new copy verifies; allow space for a third export. Clean up failed/partial or untracked exports manually. The free-space threshold does not estimate backup size.

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

For persistent use instead, adapt `config/nextcloud-automation.service.example`: set the existing service account and absolute repository/venv paths. That account needs Docker access, rclone credentials and write access to exports/state. Docker access grants host administration privileges.

```bash
sudo cp config/nextcloud-automation.service.example /etc/systemd/system/nextcloud-automation.service
sudo systemctl daemon-reload
sudo systemctl enable --now nextcloud-automation
journalctl -u nextcloud-automation -f
```

## Verify and recover

Check a scheduled backup, Telegram authorization and manual limits, then restore an external copy using [validation](validation.md). Run the [monitoring tests](monitoring.md#acceptance-test) if enabled. Local unit tests (`python -m unittest discover -s tests`) simulate external services.

Stop the service before maintenance and let an active job finish. After a crash, the persistent `active` flag blocks further work. Inspect AIO, Borg and the export helper; finish or stop the interrupted operation, restart AIO applications and confirm their health. Then, with the service stopped, run:

```bash
python scripts/automation.py recover
```

This checks that Borg/export are stopped and Nextcloud is healthy, then clears the interruption flag without resetting quotas. Inspect partial exports separately. Preserve `backup/automation/state.json`; deleting it loses quota and retention history. Use only one repository checkout/service per AIO installation. Do not migrate this state to a different installation without reviewing its recorded paths.

References: [AIO backup](https://github.com/nextcloud/all-in-one#backup), [AIO orchestration script](https://github.com/nextcloud/all-in-one/blob/main/Containers/mastercontainer/daily-backup.sh), [Telegram Bot API](https://core.telegram.org/bots/api).
