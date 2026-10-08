# Restore

For one deleted file, try Nextcloud's trash or version history first. Test full restores in a separate VM: restoring over an existing installation can overwrite newer data.

## Recover into a new Linux VM

1. Install Docker Engine and Compose (not the Docker snap). Copy this repository, your [backup export](backup.md#export-and-optionally-copy) and its SHA-256 to the VM.
2. Verify `sha256sum -c aio-backup.tar.sha256` succeeds, then extract into an empty directory:

   ```bash
   sudo mkdir -p /mnt/restore-backup
   sudo tar -xf aio-backup.tar -C /mnt/restore-backup
   ```

3. Configure `.env` for the new host. For the standard setup, install Tailscale inside the VM and use the startup helpers. Access local-only AIO administration through SSH forwarding if needed:

   ```bash
   ssh -L 18080:127.0.0.1:18080 USER@VM_ADDRESS
   ```

4. Open [AIO administration](https://localhost:18080). Save its new password and choose **Restore former AIO instance from backup** before creating a fresh Nextcloud installation.
5. Enter `/mnt/restore-backup` (the parent of `borg`) and the saved Borg password. Select the archive and restore it.
6. Configure the hostname as below if it changed, then start applications through AIO.
7. Verify original users, files, shares and collaborative Office editing. Re-enable backups and test a new backup.

## If the Tailscale hostname changed

The backup retains the old hostname. Follow the [AIO domain-change procedure](https://github.com/nextcloud/all-in-one#how-to-change-the-domain). Save protected configuration copies and stop affected services before editing.

The following opens AIO's `configuration.json`:

```bash
sudo docker run -it --rm \
  --volume nextcloud_aio_mastercontainer:/mnt/docker-aio-config:rw \
  alpine sh -c "apk add --no-cache nano && nano /mnt/docker-aio-config/data/configuration.json"
```

Replace the exact old hostname with the new one in domain/URL settings. Restart through AIO. If stale references remain, follow [Nextcloud configuration editing](https://github.com/nextcloud/all-in-one#how-to-edit-nextclouds-configphp-file-with-a-texteditor).
