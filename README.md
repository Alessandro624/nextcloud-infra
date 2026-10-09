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

## Deployment order

1. [Set up Nextcloud](docs/setup.md) and [backup storage](docs/backup.md).
2. Prepare [automation](docs/automation.md), then optional [monitoring](docs/monitoring.md), before starting the scheduler.
3. Validate [network isolation](docs/network.md) and the [security checklist](docs/security.md) on the target host.

## Guides

- [Setup and testing](docs/setup.md)
- [Full validation and test cleanup](docs/validation.md)
- [Backup](docs/backup.md)
- [Backup automation and Telegram](docs/automation.md)
- [Restore and hostname changes](docs/restore.md)
- [Security checklist](docs/security.md)
- [Network isolation](docs/network.md)
- [External monitoring](docs/monitoring.md)
- [Disaster recovery checklist](docs/disaster-recovery.md)

Git stores configuration, Docker volumes store data, and your password manager stores secrets. Backup storage supports a Docker volume or host directory, plus optional disk/NAS/rclone copies. Optional host automation provides scheduling, export retention, Telegram controls and outbound Healthchecks status reporting. Firewall enforcement and runtime validation are deployment steps.
