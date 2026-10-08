# Nextcloud infrastructure

Docker Compose configuration and operating procedures for a self-hosted Nextcloud All-in-One (AIO) installation with a domain and HTTPS. AIO manages Nextcloud, PostgreSQL, Redis, Collabora and its built-in Borg backup service.

## Quick start

Read [setup](docs/setup.md) first to configure DNS, certificates and network access.

Linux:

```bash
bash scripts/start.sh
```

Windows with Docker Desktop and Linux containers:

```powershell
./windows/start.ps1
```

Open https://localhost:8080 on the Docker host to configure AIO. Enter your actual domain in the wizard and enable Collabora. No `.env` file is required by this Compose configuration.

## Operations

Use the AIO interface to start, stop, back up, restore and update application containers. The scripts only start or stop the master container and report container status; Compose does not manage the complete AIO stack.

- [Setup and acceptance checks](docs/setup.md)
- [Backup](docs/backup.md)
- [Restore](docs/restore.md)
- [Security](docs/security.md)
- [Disaster recovery](docs/disaster-recovery.md)

Git stores configuration and procedures. Docker volumes store application state. A password manager stores credentials and recovery secrets. Google Drive is the intended destination for encrypted off-site backups; its integration and scheduling are not implemented yet.

The image follows the AIO stable `latest` channel. Record deployed versions and validate updates with a recoverable backup. See the [official AIO documentation](https://github.com/nextcloud/all-in-one).
