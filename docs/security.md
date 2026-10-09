# Security

Before using business data:

- Restrict Tailscale access to intended users; give each person a separate Nextcloud account.
- Keep administration and backend bindings on loopback for host-based Serve. Check ports published by optional AIO services.
- Enable administrator 2FA and save recovery codes outside Nextcloud.
- Restrict Docker and SSH access. Docker socket access grants powerful host privileges, even with a read-only mount.
- Keep passwords, `.env`, runtime configuration and backup exports outside Git.
- Update the OS and AIO with a verified backup available. Record deployed versions: `latest` changes over time.
- Monitor disk space and backup failures; keep an off-site copy and periodically test restore.
- Validate [network isolation](network.md), including Docker traffic and IPv6. Tailscale does not restrict general outbound Internet access.
- Configure [external monitoring](monitoring.md) with status fields only, and protect ping URLs as secrets.

## Repository review — 2026-10-09

Reviewed the management scripts, Compose defaults, backup/export/copy paths, Telegram authorization, persistent quotas, retention and outgoing Python HTTP requests.

Corrections: external copies reject unexpected files and linked archive/checksum files; Telegram and Healthchecks reject redirects and inherited proxies; Telegram outages no longer prevent scheduler startup; Docker status probes have a timeout; Healthchecks accepts only explicit HTTPS destinations and sends a fixed status schema. Monitoring failures cannot abort backup/recovery.

A targeted pattern scan of 52 historical Git blobs and the working files found no recognizable private keys or Telegram/GitHub/Tailscale/Google OAuth/AWS tokens. This is a limited pattern check, not proof that every possible secret is absent. Local ignored credentials were not collected or published.

Remaining deployment checks: host ACLs, actual published ports, tailnet policy, runtime egress, firewall denials, dependency/image vulnerabilities, monitor delivery and a real automated restore. Images use moving `latest` tags; record deployed digests and review updates. The unit tests simulate external services and do not certify a running installation.

Use [setup](setup.md) for access configuration and [backup](backup.md) for recovery preparation.
