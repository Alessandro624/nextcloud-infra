# Forgejo production runbook

Optional Linux module, independent of the Nextcloud stack. Start from a fresh installation; do not run creation commands over an existing deployment.

## Scope and assumptions

- Nextcloud, Docker, Tailscale and your external storage account already work.
- **Reference platform: Ubuntu 24.04/Debian with systemd, Docker Engine and Compose v2.** All commands below are Bash on that Linux host. If Nextcloud runs on Windows, create a dedicated Linux VM for Forgejo, install Docker/Tailscale there, and run these commands inside it. Do not paste them into PowerShell.
- Small internal team: SQLite, local SSD storage and a single Forgejo instance. SQLite is supported for modest workloads; sustained heavy concurrency needs a separate PostgreSQL design, not a database-type toggle on existing data.
- Features covered: Git HTTPS/SSH, organizations, issues, pull requests, wiki, releases, LFS, packages, optional SMTP and Actions, encrypted local/off-site backups, retention, monitoring, restore and upgrades.
- Forgejo is independent: `/srv/forgejo`, Compose project `forgejo`, private HTTPS port `8443`, SSH `2222`. Nextcloud keeps HTTPS `443` and its existing volumes, jobs and configuration.
- CI runs on a **separate, disposable runner VM**. Never give a runner the Docker socket of the Nextcloud/Forgejo host.
- Backup downtime lasts for the local snapshot scan. Forgejo restarts before uploading. Budget disk space for repositories, packages, LFS, Actions artifacts, growth and backups. An initial planning allowance of 2 vCPU and 2-4 GiB RAM is not a sizing guarantee; measure your workload. Runners need their own capacity.

Complete [acceptance](forgejo-restore.md#acceptance) on a disposable deployment before admitting business data. Keep administrative console access throughout firewall changes.

## Prepare the host

Use one root Bash session for host setup. This guide creates a new directory and stops if it already exists; do not overwrite an existing installation.

```bash
sudo -i
set -euo pipefail
# Absolute path to the trusted checkout on this host, outside /srv/forgejo.
REPO_DIR=/path/to/nextcloud-infra
test -f "$REPO_DIR/modules/forgejo/compose.yml"
umask 077
docker version
docker compose version
tailscale status
tailscale serve status
ss -lntup
test ! -e /srv/forgejo
install -d -m 700 /srv/forgejo
install -d -m 700 /srv/forgejo/config /srv/forgejo/data
install -d -m 700 /srv/forgejo/scripts /srv/forgejo/systemd
chown 1000:1000 /srv/forgejo/config /srv/forgejo/data
apt-get update
apt-get install -y restic rclone python3 curl git git-lfs sqlite3 ca-certificates nano
cd /srv/forgejo
```

Docker/Tailscale installation is assumed. Verify `127.0.0.1:13000`, `127.0.0.1:12222`, tailnet `8443` and `2222` are unused. Do not change existing Serve routes to make room.

Use local storage for SQLite and live repositories, not a Nextcloud sync folder or network filesystem. The UID `1000` is the container process identity, not a new host administrator. Keep host accounts trusted and `/srv/forgejo` root-only; filesystem access is not isolated from a host administrator.

## Pin and configure Forgejo

Choose a supported rootless release from the [official releases](https://forgejo.org/releases/). On 2026-11-02, 17.0.1 is stable and 15.0.11 is LTS; 16.x is discontinued. The example below targets a **fresh** 17.0.1 installation, not an upgrade command. Resolve its digest and validate on a disposable VM before production.

```bash
cd /srv/forgejo
docker pull codeberg.org/forgejo/forgejo:17.0.1-rootless
FORGEJO_IMAGE=$(docker image inspect codeberg.org/forgejo/forgejo:17.0.1-rootless --format '{{index .RepoDigests 0}}')
test -n "$FORGEJO_IMAGE"
printf 'FORGEJO_IMAGE=%s\n' "$FORGEJO_IMAGE" > .env
chmod 600 .env
```

Create `compose.yml`:

```bash
install -m 644 "$REPO_DIR/modules/forgejo/compose.yml" /srv/forgejo/compose.yml
```

Generate `config/app.ini`. The hostname comes from the existing Tailscale identity; confirm the output hostname is the one you intend to use. Secrets are generated locally, not passed through shell history. Keep the complete configuration, including generated keys, in encrypted backups.

```bash
cd /srv/forgejo
export FORGEJO_HOST
FORGEJO_HOST=$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
printf 'Forgejo URL: https://%s:8443/\n' "$FORGEJO_HOST"
python3 "$REPO_DIR/modules/forgejo/scripts/configure.py"
unset FORGEJO_HOST
docker compose config --quiet
docker compose up -d
docker compose logs --tail=60 forgejo
```

Only the Docker-internal HTTP listener binds all interfaces; published ports are loopback-only. The rootless image does not make the host Docker daemon rootless. No Docker socket is mounted.

`REVERSE_PROXY_LIMIT=0` avoids trusting forged forwarding headers. Client IPs in Forgejo may therefore be the proxy address; use Tailscale/firewall logs for network attribution. Do not blindly trust every Docker/private subnet to recover client IP logging.

The rootless image's default configuration path changed; `GITEA_APP_INI` explicitly selects the mounted configuration used by the admin CLI too. Without it, the web service can start with a different configuration and database, ignoring the settings above. See the [Forgejo 15 release notes](https://forgejo.org/2026-04-release-v15-0/).

Wait for startup/migrations and check the application. Verify the web process uses `-c /etc/gitea/app.ini` before creating an administrator:

```bash
docker compose exec -T forgejo ps -o pid,args
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:13000/api/healthz
docker compose exec -T forgejo forgejo --config /etc/gitea/app.ini admin user list
```

Continue only if the process path matches, health succeeds and listing users succeeds (an empty list is normal on a fresh installation). If listing reports `no such table: user`, check the process configuration path and startup logs; do not delete the database or initialize another database to hide the mismatch.

```bash
docker compose exec -T forgejo forgejo --config /etc/gitea/app.ini admin user create \
  --username forge-admin --email ADMIN_EMAIL_REPLACE_ME \
  --admin --random-password --random-password-length 32 --must-change-password
```

Replace the email before execution. Save the generated password directly in the password manager; do not redirect it into an operational log. The installation page remains locked. If the rootless image fails a capability/permission check, inspect its logs and verify the documented image paths before weakening restrictions.

## Private HTTPS and Git SSH

In the Tailscale policy, grant only the intended people access to this host's `8443` and `2222` ports. Review existing broad grants: adding a narrower grant does not cancel an existing broad one. Keep SSH administration separately restricted.

```bash
tailscale serve --bg --https=8443 http://127.0.0.1:13000
tailscale serve --bg --tcp=2222 tcp://127.0.0.1:12222
tailscale serve status
tailscale funnel status
```

Do not use `tailscale serve reset`, change port `443`, enable Funnel, or modify Nextcloud's proxy. Confirm Nextcloud still works at its previous URL.

Log in at `https://YOUR_HOST.ts.net:8443/`, change the password, enroll 2FA and store recovery codes offline. Add individual accounts through Site Administration. Use a separate non-admin account for normal development and designate a second recovery administrator.

For Git HTTPS, generate a narrowly scoped access token and store it using your OS credential manager. Password-based Git authentication is disabled. Never embed tokens into remote URLs. For SSH, upload a passphrase-protected Ed25519 public key and compare the server host-key fingerprint through an administrator before accepting it.

```bash
# On a developer workstation, substitute the actual hostname and repository.
git clone https://YOUR_HOST.ts.net:8443/TEAM/REPOSITORY.git
ssh -T -p 2222 git@YOUR_HOST.ts.net
git clone ssh://git@YOUR_HOST.ts.net:2222/TEAM/REPOSITORY.git
```

SSH authentication success may return a nonzero exit because Forgejo does not offer a shell; read the message. When offboarding a person, remove both Forgejo access/tokens and Tailscale access.

## Organizations, packages, email and outbound policy

Create a private organization, teams with the minimum repository permissions, and protected default branches. Require pull-request review for important repositories and prevent force pushes. Enable issues/wiki/releases as needed. Verify a non-member cannot access a private repository. Disable external avatars in the administration UI.

LFS and the package registry are enabled and use local storage under the backed-up data directory. Set repository/LFS/package size and retention limits in the administrative settings appropriate to your workload. Before deleting packages or Actions artifacts, agree a retention policy with the team; backups are not a replacement for sensible quotas.

Optional SMTP: edit the existing `[mailer]` section of `/srv/forgejo/config/app.ini` using a root editor, without exposing passwords in shell history. For port 587 use `PROTOCOL = smtp+starttls`, set `SMTP_ADDR`, `SMTP_PORT`, `FROM`, `USER`, `PASSWD` and `ENABLED = true`. Under `[service]`, add `ENABLE_NOTIFY_MAIL = true`. Use a dedicated sending account and valid TLS; never disable certificate verification. Restart Forgejo and send a test email from the admin UI. If SMTP stays disabled, document administrator-assisted password recovery and use UI notifications.

Enforce network policy on the host/gateway **and Docker forwarding path**, including IPv6. The Compose network is not an egress firewall. Start with these explicit flows:

| Source | Allowed destination |
| --- | --- |
| Authorized tailnet members | Forgejo HTTPS `8443`, Git SSH `2222` |
| Host Serve | Loopback `13000`, `12222` |
| Host | Approved DNS/time services, Tailscale coordination/certificates/relay infrastructure |
| Host backup process | Selected rclone storage API/authentication endpoints; Healthchecks `hc-ping.com:443` |
| Forgejo container | Only selected SMTP endpoint if enabled; explicitly reviewed integrations |
| Host during maintenance | Forgejo image registry and OS package repositories |
| Runner VM | Forgejo HTTPS and explicitly approved CI image/dependency endpoints |

No direct Forgejo Internet access is required for basic local Git/issue/wiki hosting. Disable unused mirroring/migration/webhooks and external integrations; allow each destination separately when introduced. Firewall rules, not `OFFLINE_MODE`, enforce isolation. Observe startup, LFS/package transfers, idle time, backup and Actions traffic; prove an unapproved destination is denied from both host and container. Keep captures private. Do not copy broad Nextcloud network permissions into Forgejo.

Next: [backup and monitoring](forgejo-backup.md), then [restore and acceptance](forgejo-restore.md). Optional: [Telegram bot](forgejo-telegram.md).
