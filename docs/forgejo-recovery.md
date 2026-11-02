# Forgejo backup recovery

Installed as part of [backup setup](forgejo-backup.md). No separate patch is required.

## Behavior

- The same `forgejo-backup.service` serves the daily timer, Telegram requests and recovery. The existing exclusive lock is retained.
- `pending.json` is atomically written and synced under `/var/lib/forgejo-backup` before stopping the application. A successful snapshot ID and destination configuration are persisted before upload.
- Failed jobs retry after five minutes. After a reboot, a separate timer requests the same service only if a pending job exists.
- If interrupted while Forgejo was stopped, restart and check application health first. If the local snapshot was not durably recorded as successful, create a fresh one. Partial snapshots (including restic exit 3) are never copied as successful backups.
- A completed snapshot is reused for off-site retry, without stopping Forgejo again. Copy and checks repeat safely; retention runs only after successful verification. Weekly full-data verification follows the original job's Sunday setting.
- Pending work takes precedence over a new daily/manual backup. A long outage therefore delays new local snapshots. Retries do not consume new Telegram quotas.
- Each restic command has a four-hour deadline; expired commands and their subprocesses are terminated before retry. Adjust in code for repositories requiring longer checks. Active commands may perform their own network retries before returning.

Normal `restic unlock` removes stale locks only; `--remove-all` is never used. These must remain single-writer dedicated repositories: do not run other maintenance, restore tools or a restored server against them concurrently. A lock may need time to become stale. Configuration changes, corruption, full disks, lost credentials or hardware failures require operator correction; this does not guarantee recovery from every failure.

Healthchecks reports failure and eventual successful completion. Notifications are bounded/best effort: a lost success ping alone is not persisted for replay. Keep the independent service-health check enabled.

## Acceptance on a disposable deployment

1. Interrupt network access during `External copy`, after Forgejo has restarted. Require pending state and no retention after failure. Restore access and wait for retry; require the same snapshot ID, no second local backup/downtime, and a verified off-site copy.
2. Reboot during a pending upload. After boot, require automatic resume and successful completion.
3. Simulate abrupt power loss in an isolated VM during `Local snapshot`. After boot, require application recovery, a new complete snapshot if needed, and no partial snapshot promotion. A graceful reboot does not fully test power loss.
4. Try a second backup request during work/retry; it must not create a parallel writer. Verify the bot's quotas remain unchanged by automatic retries.
5. Test failed verification: no retention, pending state preserved, failure notification. Correct the underlying fault; do not clear state or force-unlock.
6. Complete a restore drill from the off-site repository. Unit tests cannot validate restic/MEGA durability, systemd, power loss or actual restoration.

Run local simulations: `python -m unittest discover -s modules/forgejo/automation -p "test_*.py"`.

## Maintenance

Disable bot backup requests and both backup timers. Let active/pending work finish; then stop the idle backup service to cancel retries before replacing scripts. Preserve `/var/lib/forgejo-backup` and never delete `pending.json` to clear an error. Update only code and units from the trusted checkout; keep credentials and state. Validate units, reload systemd and repeat failure/restore tests before enabling both timers and bot requests again.

The application snapshot does not include `/etc/forgejo-backup`, `/var/lib/forgejo-backup`, `/etc/forgejo-bot` or `/var/lib/forgejo-bot`. Store these and any unit overrides in a separately encrypted recovery kit. Never run production and restored writers/bots concurrently.
