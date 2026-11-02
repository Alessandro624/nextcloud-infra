# Forgejo (optional)

Independent Compose project, backup workflow and Telegram bot. Nothing is installed by cloning this repository. Nextcloud does not back up this module.

Follow [setup](../../docs/forgejo-setup.md), [backup and monitoring](../../docs/forgejo-backup.md), then [restore/acceptance](../../docs/forgejo-restore.md). Add the [bot](../../docs/forgejo-telegram.md) only after backup validation. [Actions](../../docs/forgejo-actions.md) requires a separate runner VM.

## Reference layout

| Item | Default |
| --- | --- |
| Host | Dedicated Debian/Ubuntu, systemd, Docker Engine and Compose v2 |
| Application and snapshot source | `/srv/forgejo` |
| HTTP / SSH backend | Loopback `13000` / `12222` |
| Tailscale HTTPS / Git SSH | `8443` / `2222` |
| Local restic repository | `/var/backups/forgejo/restic` |
| Backup credentials | `/etc/forgejo-backup` (root only) |
| Durable backup state | `/var/lib/forgejo-backup` |
| Bot configuration / state | `/etc/forgejo-bot` / `/var/lib/forgejo-bot` |

These are shared reference defaults, not discovered production values. Keep them for the documented installation. Changing application paths or ports requires updating Compose, generated app.ini, health checks, backup scripts, units, bot configuration and restore instructions together. The backup workflow intentionally rejects a different local repository path.

Configure the image digest in the installed `.env`, the hostname through the setup generator, the storage remote in `/etc/forgejo-backup/environment`, and bot IDs/token locally. The timer, bot and Healthchecks schedule must agree. Never commit generated configuration, state or credentials.

## Validation

```bash
python3 -m unittest discover -s modules/forgejo/automation -p 'test_*.py'
python3 -m unittest discover -s modules/forgejo/bot -p 'test_*.py'
python3 -m unittest discover -s modules/forgejo/scripts -p 'test_*.py'
```

These simulations exercise failures, quota checks and recovery ordering. They do not validate Docker/systemd integration, provider durability, power loss or a real restore. Complete the [clean-machine validation](../../docs/modules-validation.md) before deployment.
