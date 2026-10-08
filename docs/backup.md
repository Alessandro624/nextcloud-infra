# Backup

Choose one primary AIO/Borg destination and, optionally, an external copy. A disk or NAS in the same building is external storage, not necessarily off-site.

## Configure

Install Python 3 (`python` on Windows, `python3` on Linux). Copy `config/backup.example.json` to `config/backup.json`, which is ignored by Git.

| Setting | Options |
| --- | --- |
| `source_type` | `volume` (default) or `path` |
| `source` | Docker volume name or absolute Docker-host directory |
| `export_directory` | Staging directory; relative paths resolve from the repository |
| `copy_type` | `none`, `local` or `rclone` |
| `copy_destination` | Existing absolute directory or configured `remote:path` |

Examples (edit the corresponding settings):

- Docker volume: `source_type=volume`, `source=nextcloud_aio_backupdir`.
- Linux disk/mounted NAS: `source_type=path`, `source=/mnt/nextcloud-backup`.
- Windows folder: create `D:\nextcloud-backup`, then use `source_type=path`, `source=/run/desktop/mnt/host/d/nextcloud-backup`. Verify Docker Desktop can access it.
- USB/NAS copy: `copy_type=local`, `copy_destination=E:/nextcloud-copies` on Windows or `/mnt/offsite/nextcloud` on Linux. Mount and create it first.
- Remote copy: `copy_type=rclone`, `copy_destination=offsite:nextcloud`. Configure `offsite` with `rclone config` for your supported provider (Drive, S3, SFTP, etc.). Keep credentials outside this JSON and Git.

Settings are JSON strings, not shell assignments. Defaults apply when the local configuration is absent. Changing configuration does not migrate data or change AIO's saved destination.

## Create the primary backup

1. Startup scripts run `python scripts/backup.py prepare`: volume mode creates/reuses the volume; path mode prints the directory you must prepare.
2. Select the printed destination in AIO, save the Borg encryption password, then run a backup and its integrity check.
3. A primary backup on the same disk does not protect against disk loss.

## Export and optionally copy

Commands below use Windows `python`; use `python3` on Linux. Run from this repository on the Docker host, with Docker permissions.

1. Finish the AIO backup/integrity check. Stop applications through AIO, then run `docker stop nextcloud-aio-mastercontainer`. Keep AIO and all external Borg writers stopped during export.
2. Run:

   ```bash
   python scripts/backup.py export
   ```

3. The command prints a timestamped export directory containing `aio-backup.tar` and its SHA-256. Use that exact directory:

   ```bash
   python scripts/backup.py copy --export backup/exports/GENERATION
   ```

   Skip this command when `copy_type=none`. Once export finishes, AIO can be restarted while the separate copy runs.

Local copies are checksum-verified and refuse overwrites. Remote copies use rclone's immutable copy and download verification, then publish `COPY-VERIFIED.txt`. Download verification reads the full remote archive and may incur transfer costs. Failed exports/local copies retain `.partial-*` directories; failed remote copies lack a success marker. Resolve the failure before retrying or removing partial files.

Each export contains the full Borg repository: allow space for staging and retained copies. No automatic deletion or scheduling is performed. A successful copy proves byte transfer, not backup freshness or recoverability.

## Recover and operate

Retrieve a complete generation from your disk/NAS or with `rclone copy offsite:nextcloud/GENERATION backup/recovered`. Run `python scripts/backup.py verify --export backup/recovered`, then follow [restore](restore.md).

Configure primary scheduling/retention in AIO. External scheduling, retention cleanup, failure notifications and live locked exports remain future work. Test an actual restore from your chosen external storage before relying on it.

References: [AIO backup](https://github.com/nextcloud/all-in-one#backup), [rclone verification](https://rclone.org/commands/rclone_check/).
