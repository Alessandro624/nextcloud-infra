# Security

Before using business data:

- Restrict Tailscale access to intended users; give each person a separate Nextcloud account.
- Keep administration and backend bindings on loopback for host-based Serve. Check ports published by optional AIO services.
- Enable administrator 2FA and save recovery codes outside Nextcloud.
- Restrict Docker and SSH access. Docker socket access grants powerful host privileges, even with a read-only mount.
- Keep passwords, `.env`, runtime configuration and backup exports outside Git.
- Update the OS and AIO with a verified backup available. Record deployed versions: `latest` changes over time.
- Monitor disk space and backup failures; keep an off-site copy and periodically test restore.

Use [setup](setup.md) for access configuration and [backup](backup.md) for recovery preparation.
