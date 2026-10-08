# Disaster recovery

If the server or disk is lost:

1. Retrieve this repository, a complete off-site Borg backup and its encryption password.
2. Prepare a replacement host and follow [restore](restore.md).
3. Configure the new hostname/access route and verify users, files, permissions and Office editing.
4. Reconnect users and sync clients only after validation.
5. Re-enable backups and confirm a new local and off-site recovery point.
6. Record recovery time and any data lost since the selected backup.

Assign a recovery owner and substitute. Keep backup-account access and recovery secrets available without Nextcloud.
