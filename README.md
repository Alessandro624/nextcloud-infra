# Nextcloud infrastructure

Self-hosted Nextcloud AIO with collaborative Office editing and private HTTPS access through Tailscale. Tested on Windows/Docker Desktop, with backup restored into an Ubuntu VM.

## Start here

Install Docker, Python 3 and Tailscale, sign in, then follow [setup](docs/setup.md).

Windows:

```powershell
./windows/start.ps1
./windows/tailscale.ps1
```

Linux (Docker access and Python 3 required):

```bash
bash scripts/start.sh
bash scripts/tailscale.sh
```

Open [AIO administration](https://localhost:18080). Enter the Tailscale hostname in the wizard, enable Collabora and start the applications. Use the Tailscale HTTPS URL to access Nextcloud.

Startup creates `.env` from `.env.example` if missing. Edit it to change ports and bind addresses. Use AIO to manage applications; Compose manages only the master container.

## Guides

- [Setup and testing](docs/setup.md)
- [Backup](docs/backup.md)
- [Restore and hostname changes](docs/restore.md)
- [Security checklist](docs/security.md)
- [Disaster recovery checklist](docs/disaster-recovery.md)

Git stores configuration, Docker volumes store data, and your password manager stores secrets. Backup storage supports a Docker volume or host directory, plus optional disk/NAS/rclone copies. External scheduling, retention cleanup and monitoring remain pending.
