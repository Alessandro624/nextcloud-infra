# Standalone Forgejo Telegram bot

Separate token, process and systemd service. Nextcloud code remains unchanged. Requires the existing `forgejo-backup.service` from [the Forgejo guide](forgejo-backup.md), Python 3.10+, sudo and systemd on the same Linux host.

## Install

Create a new bot with **@BotFather: /newbot**, then open it and press Start. Do not reuse the Nextcloud token or configure a webhook.

On the Debian server, start in the trusted repository checkout.

On Debian, first installation only:

```bash
test -f modules/forgejo/bot/forgejo_bot.py
sudo test ! -e /etc/forgejo-bot/config.json || exit 1
sudo test ! -e /etc/forgejo-bot/token.secret || exit 1
id forgejo-bot >/dev/null 2>&1 || sudo useradd --system --user-group --home-dir /var/lib/forgejo-bot --shell /usr/sbin/nologin forgejo-bot
sudo install -d -o root -g root -m 755 /opt/forgejo-bot
sudo install -d -o root -g forgejo-bot -m 750 /etc/forgejo-bot
sudo install -d -o forgejo-bot -g forgejo-bot -m 700 /var/lib/forgejo-bot
sudo install -o root -g root -m 644 modules/forgejo/bot/forgejo_bot.py /opt/forgejo-bot/forgejo_bot.py
sudo install -o root -g root -m 644 modules/forgejo/bot/forgejo-bot.service /etc/systemd/system/forgejo-bot.service
sudo install -o root -g forgejo-bot -m 640 modules/forgejo/bot/config.example.json /etc/forgejo-bot/config.json
sudo install -o root -g forgejo-bot -m 640 /dev/null /etc/forgejo-bot/token.secret
sudo python3 - <<'PY'
from getpass import getpass
from pathlib import Path
Path('/etc/forgejo-bot/token.secret').write_text(getpass('New Forgejo bot token: ').strip() + '\n')
PY
```

Do not repeat config/token installation on upgrades: it overwrites settings. Keep code and units root-owned and not writable by the bot. Do not add the bot user to Docker or administrative groups. Never paste the token into a chat or URL.

## Configure

Send a message to the new bot, then discover IDs locally with the service stopped:

```bash
sudo -u forgejo-bot /usr/bin/python3 /opt/forgejo-bot/forgejo_bot.py discover
sudoedit /etc/forgejo-bot/config.json
```

Discovery prints numeric user/chat IDs only. If empty, send another message and retry. For groups, use the group chat ID and each authorized human user ID. Set **both** `user_ids` and `chat_ids` after reviewing identities.

| Setting | Default / meaning |
| --- | --- |
| `http_port` | 13000, loopback Forgejo backend |
| `scheduled_time`, `timezone` | 03:30, Europe/Rome; match the existing backup timer |
| `manual_daily_limit`, `manual_weekly_limit` | 1 attempt per rolling 24h, 3 per rolling 7 days, shared by authorized users |
| `minimum_interval_hours` | 6h cooldown; also reserves 6h before/after the daily scheduled time |
| `poll_seconds` | 300, notification polling interval |
| `backup_enabled` | false until restricted sudo permission is installed |

State, quotas and Telegram offsets persist in `/var/lib/forgejo-bot/state.json`. Never delete it to clear an error. A start attempt consumes quota even if rejected or its result is uncertain. Confirmation is single-use and expires after 60 seconds. Messages older than 60 seconds are ignored.

## Permit only backup start

Inspect the existing privileged service and timer:

```bash
command -v sudo systemctl
sudo systemctl cat forgejo-backup.service
sudo systemctl list-timers forgejo-backup.timer --no-pager
sudo -u forgejo-bot systemctl show forgejo-backup.service --no-pager -p LoadState -p ActiveState -p Result -p ExecMainStatus
sudo stat -c '%U:%G %a %n' /srv/forgejo/scripts/backup.sh /etc/systemd/system/forgejo-backup.service
```

Require `/usr/bin/sudo` and `/usr/bin/systemctl`. Keep the existing backup script's exclusive `flock`, checks and application recovery. Privileged scripts, configuration and parent directories must be administrator-owned and not writable by the bot. Do not grant the permission otherwise.

Run `sudo visudo -f /etc/sudoers.d/forgejo-bot` and enter exactly:

```sudoers
forgejo-bot ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block forgejo-backup.service
```

Validate without starting a backup:

```bash
sudo chmod 440 /etc/sudoers.d/forgejo-bot
sudo visudo -cf /etc/sudoers.d/forgejo-bot
sudo -l -U forgejo-bot
```

Then set `backup_enabled` to `true`. Do not allow arbitrary systemctl commands. `NoNewPrivileges` is deliberately absent from the unit because it prevents the narrow sudo elevation. The bot has no restic/rclone secrets or restore/delete commands. These quotas govern bot requests, not an administrator or a compromised bot OS account with the same sudo permission.

## Start and validate

```bash
sudo -u forgejo-bot /usr/bin/python3 /opt/forgejo-bot/forgejo_bot.py check
curl --fail --max-time 5 http://127.0.0.1:13000/api/healthz
sudo systemctl daemon-reload
sudo systemctl enable --now forgejo-bot
sudo journalctl -u forgejo-bot -f
```

Require JSON `status: pass` from the health endpoint. `check` validates settings only, not connectivity or sudo permissions.

| Command | Result |
| --- | --- |
| `/help` | Command list |
| `/status` | HTTP health and backup unit status |
| `/backup_status` | Current/last execution result from systemd |
| `/backup` | Confirm and request the existing Forgejo backup service |

- Test status commands and verify unauthorized users or chats receive no response.
- On a disposable deployment, request one backup outside the reservation window. Verify off-site completion and application recovery. Repeat requests must hit quotas/cooldown; expired confirmations must do nothing.
- Stop/start Forgejo outside backup on the test deployment; expect failure/recovery alerts within the polling interval.
- Interrupt Telegram connectivity: the backup continues. Polling retries every 10 seconds; failed alerts retry at subsequent polls. Restart the bot and verify quotas remain.

Notifications report state changes and recovery; repeated success is quiet. Polling can miss brief failures. HTTP downtime is tolerated for up to two hours while the backup unit runs. `unknown` means systemd has no completed run recorded, often after reboot; it does not mean archives disappeared. `success` is the script's exit result, not independent archive/restore verification. Keep Healthchecks for missed schedules and host-offline alerts.

This bot itself does **not** retry failed restic uploads or alter retention. Install the separate [backup recovery upgrade](forgejo-recovery.md) for persistent retries; the updated bot reports `retrying` during the systemd retry wait. The existing backup service continues if the bot stops. Scheduled/operator jobs do not consume bot quotas; a recent observed unit start still enforces cooldown. Never run an independent backup script concurrently: every execution must retain the existing exclusive lock.

## Update or disable

Stop only `forgejo-bot`, install updated Python/unit files, daemon-reload and start. Preserve config, token and state; never stop an active backup service merely to update the bot.

To disable:

```bash
sudo systemctl disable --now forgejo-bot
sudo rm /etc/sudoers.d/forgejo-bot
```

Keep local state/config until deciding whether to reinstall. Rotate an exposed token through BotFather. The existing `/srv/forgejo` backup excludes this separate integration. Preserve `/opt/forgejo-bot`, `/etc/forgejo-bot`, `/var/lib/forgejo-bot`, the systemd unit and sudoers rule privately in the recovery kit. Do not loosen `/srv/forgejo` permissions for the bot. Never run original and restored bots simultaneously.

Network: outbound Telegram HTTPS, loopback Forgejo HTTP and the local systemd bus; no inbound port or webhook.

Local simulated tests: `python -m unittest discover -s modules/forgejo/bot -p "test_*.py"`. Validate Linux systemd/sudo separately on the server.
