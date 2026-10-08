# Nextcloud infrastructure

Docker Compose configuration and operating procedures for a self-hosted Nextcloud All-in-One (AIO) installation with private HTTPS access through Tailscale Serve. AIO manages Nextcloud, PostgreSQL, Redis, Collabora and its built-in Borg backup service.

## Quick start

Install Docker and Tailscale on the host, sign in to Tailscale, then follow [setup](docs/setup.md). Copy `.env.example` to `.env` to customize ports and bind addresses; start scripts create it if missing.

Linux:

```bash
bash scripts/start.sh
bash scripts/tailscale.sh
```

Windows with Docker Desktop and Linux containers:

```powershell
./windows/start.ps1
./windows/tailscale.ps1
```

Open https://localhost:18080 on the Docker host (or your configured administration port). Enter the hostname printed by Tailscale Serve in the AIO wizard and enable Collabora. Use the Tailscale HTTPS URL for Nextcloud itself. `.env` remains outside Git; `.env.example` is the shared template.

## Operations

Use the AIO interface to start, stop, back up, restore and update application containers. The scripts only start or stop the master container and report container status; Compose does not manage the complete AIO stack.

- [Setup and acceptance checks](docs/setup.md)
- [Backup](docs/backup.md)
- [Restore](docs/restore.md)
- [Security](docs/security.md)
- [Disaster recovery](docs/disaster-recovery.md)

Git stores configuration and procedures. Docker volumes store application state. A password manager stores credentials and recovery secrets. Google Drive is the intended destination for encrypted off-site backups; its integration and scheduling are not implemented yet.

The image follows the AIO stable `latest` channel. Record deployed versions and validate updates with a recoverable backup. See the [official AIO documentation](https://github.com/nextcloud/all-in-one).
