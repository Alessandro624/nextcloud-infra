# Backup

Use AIO's integrated Borg backup rather than independently copying live database or application volumes. Off-site transfer and scheduling are not automated by this repository.

1. Configure a backup location through AIO, preferably on storage separate from the data disk.
2. Store the Borg recovery password, administrator credentials, 2FA recovery codes and rclone credentials in the company password manager. Verify emergency access without the Nextcloud server.
3. Run a backup and the AIO integrity check. Record the date, result and duration without secrets.
4. Copy a complete, consistent repository off-site only when no backup, prune or check can modify it. Prefer an immutable filesystem snapshot for the transfer.
5. Configure rclone with a dedicated Google Drive account. Keep OAuth tokens and `rclone.conf` outside Git.
6. Keep separate remote generations or another tested retention strategy. Incremental copy can leave obsolete Borg segments; sync can propagate deletions. Do not automate either without a recovery design.
7. Download a complete generation into an empty directory, verify integrity and perform an isolated AIO restore. Successful transfer alone does not prove recoverability.

Suggested initial targets: nightly backups, an alert after 48 hours without success, and retention of 7 daily, 4 weekly, 12 monthly and 3 yearly recovery points. Size the storage first, then configure `BORG_RETENTION_POLICY` through AIO's supported options. These targets are not active configuration.

Future automation must coordinate all Borg operations and transfer, check backup success and age, verify remote content, and report failures. Preserve the complete backup directory structure expected by AIO restore.

Record the password-manager entry location in your internal operations inventory, not the recovery password itself.

Reference: [AIO backup and restore](https://github.com/nextcloud/all-in-one#how-to-backup-and-restore).
