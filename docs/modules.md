# Optional modules

The core stack remains Nextcloud AIO. Install only what you need; modules have separate data, credentials, services and restore procedures.

| Module | Start here | Scope |
| --- | --- | --- |
| Forgejo | [Setup](forgejo-setup.md) | Private Git hosting on Linux |
| Forgejo backups | [Backup](forgejo-backup.md) | Local encrypted restic repository, separate external copy and persistent retries |
| Forgejo Telegram | [Bot](forgejo-telegram.md) | Separate token/process, allowlists and backup quotas |
| Homepage | [Setup](homepage-setup.md) | Static private portal; no application credentials |
| Debian baseline | [Hardening](debian-server-hardening.md) | Host administration and maintenance |
| Network | [Preparation](debian-network-preparation.md), [egress review](debian-egress-hardening.md) | Inventory, controlled ingress and deployment-specific egress design |

## Installation order

1. Prepare a dedicated Linux host and console recovery. Review the Debian baseline.
2. Complete [Nextcloud setup](setup.md), [backup](backup.md), [automation](automation.md) and [monitoring](monitoring.md).
3. If selected, install Forgejo, its backup/monitoring and optional bot. Test restoration.
4. Publish the homepage and validate Tailscale access rules. Repeat Office checks after tagging the host.
5. Complete network preparation, [Office/DNS checks](tailscale-office.md), egress review and [security acceptance](security.md).
6. Run [clean-machine validation](modules-validation.md); save actual results privately.

The Linux modules do not run natively on Windows/Docker Desktop. Use a Linux VM for those modules. The network guides do not install a universal outbound firewall: allowed destinations and forwarding paths must be reviewed and tested on each deployment.

`backup/` remains private. Public instructions and executable templates live in `docs/` and `modules/`; they must not depend on files in that private directory.
