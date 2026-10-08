# Restore

For a single file, first try Nextcloud's trash and version history. If necessary, restore a backup in an isolated environment and recover the file from there.

For a complete AIO installation:

1. Identify the backup generation and last successful backup time. Retrieve the Borg recovery password.
2. Prepare an isolated host with Docker and sufficient storage, with production clients disconnected.
3. Download the full off-site generation into an empty directory, preserving AIO's backup directory structure. Do not merge it into an active Borg repository.
4. Start the AIO master and select the existing-backup restore workflow. Follow the [official procedure](https://github.com/nextcloud/all-in-one#how-to-backup-and-restore), checking versions and paths before confirming.
5. Verify administrator access, users, files, shares and simultaneous DOCX/XLSX editing.
6. After validation, update DNS and reconnect clients. Re-enable backups and check the first new backup.

A full restore can overwrite changes made after the selected backup. Test recovery before relying on it for business data.
