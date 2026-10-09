# Healthchecks monitoring

Optional, outbound-only monitoring. Healthchecks cannot connect to Nextcloud through this integration: no listener, webhook, management API key or remote command handler is added. The server posts HTTPS requests and only checks the acknowledgement. Network isolation still requires [firewall validation](network.md).

## Configure

1. Create two checks in Healthchecks and configure their alert recipients there. Alerts must be sent by Healthchecks itself so they work when this server is offline.
2. For **scheduled backup**, select cron `0 2 * * *`, timezone `Europe/Rome`, matching your automation settings. Start with a 2-hour grace period, then adjust to measured backup/export/upload duration. Only scheduled jobs signal this check; manual jobs cannot hide a missed scheduled run.
3. For **service health**, select a 5-minute period and a 5-minute grace period. The local interval defaults to 300 seconds. A missed heartbeat normally alerts after period plus grace; an explicit failure can alert sooner.
4. Copy `config/healthchecks.example.json` to `config/healthchecks.json`, set `enabled` to `true`, and create `credentials/healthchecks.secret` locally:

   ```json
   {
     "backup": "https://hc-ping.com/REPLACE_WITH_BACKUP_UUID",
     "service": "https://hc-ping.com/REPLACE_WITH_SERVICE_UUID"
   }
   ```

5. Use each check's base UUID ping URL. The placeholders above are deliberately invalid. URLs must be distinct, HTTPS, on port 443, without query strings or credentials. Self-hosting is supported with an explicitly allowed hostname and a root UUID endpoint; do not use a path prefix or slug URL.
6. Restrict the secret file to the service account and administrators. On Linux, use `chmod 700 credentials` and `chmod 600 credentials/healthchecks.secret`. On Windows, remove inherited access for unrelated users in the file's Security properties. Both the local configuration and secret file are ignored by Git.
7. Run `python scripts/automation.py check`, then restart the automation service. `check` validates local URLs but sends nothing. Confirm both checks in Healthchecks before relying on alerts.

No account or check is created automatically. A ping URL is a secret: someone who obtains it could forge a success signal. Do not paste it into screenshots, shell history or committed files.

## What leaves the server

Each POST contains a small JSON status record with these fields only:

| Fields | Meaning |
|---|---|
| `schema`, `observed_at` | Schema version and Unix timestamp |
| `nextcloud`, `apache` | Docker health status, including stopped/unknown |
| `phase`, `workflow_active`, `maintenance` | Current workflow and bounded planned downtime |
| `scheduler_alive` | Scheduler has advanced recently |
| `last_backup`, `last_copy` | Unix timestamps of recorded successes, or null |
| `export_free_gib` | Free export-filesystem space, or null |
| `error_code` | Fixed code such as `LOW_SPACE`, `WORKFLOW_FAILED`, `RECOVERY_REQUIRED` |

Raw logs, exceptions, file names, usernames, hostnames, local paths, credentials and document contents are excluded. Healthchecks also sees the public source IP and request times. It stores the status body as a ping log; review its retention and account access settings.

Service health reports planned downtime during backup/export/restart without claiming the containers are healthy. After `maximum_workflow_seconds` (default 7200), a still-active workflow is reported failed. This threshold alerts; it does not kill Borg or a transfer. During other phases Nextcloud and Apache must be healthy. Low disk space, interrupted work and a stalled scheduler also fail the check. This is not an end-to-end Office or login test.

Backup success is queued after verified copy and retention complete. A separate sender samples status when delivering each event; a separate thread sends service heartbeats. The bounded, in-memory event queue is not replayed after a crash. Monitoring failures cannot block backup/recovery; missing deliveries are detected externally. Requests have a 5-second socket timeout (configurable 1–10 seconds), no immediate retry, no redirects and no inherited HTTP proxy. DNS resolution depends on the host resolver. Response content is never executed. A firewall must enforce the destination policy.

## Acceptance test

- Inspect a service ping body: only the documented fields should appear.
- Complete a scheduled backup: expect start then success. Complete a manual backup: expect updated service timestamps, without resetting the scheduled check.
- Stop the automation service while idle and wait for the missing-heartbeat alert; restart and verify recovery.
- On the disposable test deployment, stop Apache outside a backup: expect service failure; restart it and verify recovery.
- Make the test external destination unavailable: expect backup failure and no success ping. Restore connectivity and run a successful backup.
- Block Healthchecks egress: backup and Nextcloud recovery must still finish, while Healthchecks reports missing signals. Unblock and confirm heartbeat recovery.
- Confirm the alert arrives when the server is powered off. This tests the external notification route, not the local Telegram bot.

References: [ping API and attached status bodies](https://healthchecks.io/docs/http_api/), [periods, schedules and grace periods](https://healthchecks.io/docs/configuring_checks/).
