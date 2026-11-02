# Forgejo restore and maintenance

## Restore on a separate machine

Run this on a **fresh isolated Linux VM**, never over a running installation. Keep its backup timers disabled, block SMTP/webhooks/runner connections, and do not let it operate concurrently as the production identity. Install Docker, Compose, restic, rclone, Python, sqlite3, curl and Tailscale. Recover the `/etc/forgejo-backup` files from the separate recovery kit with root-only permissions. Restic normally writes repository locks even for reads: use read-only storage credentials only if your documented recovery procedure accounts for locking; never run retention from the recovery VM.

```bash
sudo -i
set -euo pipefail
umask 077
test ! -e /srv/forgejo
set -a
source /etc/forgejo-backup/environment
set +a
restic -r "$REMOTE_REPO" snapshots --host forgejo --tag forgejo
```

Choose a successful snapshot by its ID and timestamp. A database migration rollback requires the complete pre-upgrade snapshot, including its pinned image.

```bash
read -r -p 'Snapshot ID to restore: ' SNAPSHOT
[[ "$SNAPSHOT" =~ ^[0-9a-f]{8,64}$ ]]
install -d -m 700 /srv/forgejo-restore
restic -r "$REMOTE_REPO" check --read-data
restic -r "$REMOTE_REPO" restore "$SNAPSHOT" --target /srv/forgejo-restore
test -f /srv/forgejo-restore/srv/forgejo/config/app.ini
test -f /srv/forgejo-restore/srv/forgejo/data/forgejo.db
test "$(sqlite3 /srv/forgejo-restore/srv/forgejo/data/forgejo.db 'PRAGMA integrity_check;')" = ok
mv /srv/forgejo-restore/srv/forgejo /srv/forgejo
cd /srv/forgejo
chown -R 1000:1000 config data
chmod 700 config data
chmod 600 config/app.ini .env
```

Before starting, edit only `DOMAIN`, `ROOT_URL` and `SSH_DOMAIN` for the recovery VM's own Tailscale hostname. Preserve the database and all signing/encryption keys. Keep SMTP and Actions disabled during the drill. Do not regenerate `SECRET_KEY`; it is needed for stored secrets/2FA. Do not start the timers or restore the production Tailscale identity from another machine.

```bash
docker compose config --quiet
docker compose pull
docker compose up -d
curl -fsS --max-time 10 http://127.0.0.1:13000/api/healthz
tailscale serve --bg --https=8443 http://127.0.0.1:13000
tailscale serve --bg --tcp=2222 tcp://127.0.0.1:12222
```

Verify login/2FA, permissions, branches/tags, issue comments, wiki, releases/attachments, LFS files and packages. Run `git fsck --full` in a fresh clone. Record recovery time and the newest recovered commit. A mirror clone alone does not restore issues, settings, accounts, artifacts or packages.

For real disaster recovery, switch users to the replacement only after validation. Then restore the intended access rules, SMTP/Actions, local backup disk and timers. Re-register disposable runners rather than restoring their credentials blindly. Keep the old machine offline until you have prevented duplicate jobs. Remove the test VM through your hypervisor only after confirming its exact identity; this runbook deliberately contains no broad cleanup commands.

## Maintenance and future public domain

For Forgejo upgrades:

1. Read the release notes and upgrade path; choose a supported security-patched version. Schedule downtime and pause runner jobs.
2. Disable bot backup requests. Stop both `forgejo-backup.timer` and `forgejo-backup-recovery.timer`, let active or pending work complete, then run one successful backup and record its snapshot ID. Stop `forgejo-backup.service` only when idle to cancel a waiting retry. Do not update with pending work. Pause the service-health check in Healthchecks for the maintenance window.
3. Pull the chosen rootless image, inspect its digest as in [setup](forgejo-setup.md), update only `FORGEJO_IMAGE` in `.env`, and run `docker compose up -d` from `/srv/forgejo`.
4. Check logs, login/2FA, clone/push, LFS, packages and CI. Re-enable both backup timers and bot requests and unpause the health check. Confirm a post-upgrade backup.
5. If database migrations occurred, rollback means restoring the full pre-upgrade snapshot and image on an isolated/replacement installation. Merely downgrading the image against a migrated database can fail.

Keep scheduled OS/Docker/restic/rclone updates and an image vulnerability review. Avoid automatic unattended Forgejo major-version changes. Do not use global Docker prune or Nextcloud cleanup commands for Forgejo maintenance.

For a future `git.your-domain.example` endpoint, first decide private versus public exposure. Configure DNS, TLS and a dedicated reverse-proxy route, then update `ROOT_URL`, `DOMAIN` and `SSH_DOMAIN`. Review forwarded-header trust, tailnet/public access rules, OAuth redirects, runner URLs and Git remotes. Do not replace Nextcloud's existing route or assume the Tailscale certificate covers your own domain.

## Acceptance

- [ ] Nextcloud remains reachable and its scheduled backup still works.
- [ ] Forgejo image/runner digests recorded; no arbitrary `latest` tags.
- [ ] Authorized users can access Forgejo; unauthorized tailnet and LAN users cannot reach it or its backend.
- [ ] Individual accounts, mandatory 2FA, recovery codes, branch protection and non-admin daily access verified.
- [ ] HTTPS clone/push with scoped token and SSH clone/push verified; password authentication and open registration rejected.
- [ ] Issues, wiki, release attachment, LFS upload/download and one package round-trip verified.
- [ ] SMTP delivery verified if enabled; otherwise password recovery ownership documented.
- [ ] Container/host egress restricted; an unapproved IPv4/IPv6 destination produces a firewall denial.
- [ ] First local/off-site backup succeeds; encryption password and recovery kit stored separately.
- [ ] Remote restore succeeds on a fresh VM, including SQLite, account/2FA, repository data and attachments.
- [ ] Simulated backup destination failure does not prune good snapshots and Forgejo restarts.
- [ ] Healthchecks alerts on application failure and host/service absence; monitoring failure does not break backup recovery.
- [ ] Backup/health timers survive reboot; no overlapping heavy Nextcloud/Forgejo jobs.
- [ ] Actions runner isolated and tested, or explicitly left disabled until its VM is ready.
- [ ] Recovery owner, update schedule, capacity thresholds and restore-drill schedule recorded.

## Official references

- [Forgejo release/download](https://forgejo.org/download/) and [Docker installation](https://forgejo.org/docs/latest/admin/installation/docker/).
- [Forgejo configuration](https://forgejo.org/docs/latest/admin/config-cheat-sheet/), [CLI](https://forgejo.org/docs/latest/admin/command-line/) and [database recommendations](https://forgejo.org/docs/latest/admin/setup/recommendations/).
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).
- [restic repository setup](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html), [copying repositories](https://restic.readthedocs.io/en/stable/045_working_with_repos.html) and [retention](https://restic.readthedocs.io/en/stable/060_forget.html).
- [Healthchecks ping API](https://healthchecks.io/docs/http_api/).
- [Runner installation](https://forgejo.org/docs/latest/admin/actions/installation/docker/), [configuration](https://forgejo.org/docs/latest/admin/actions/configuration/), [registration](https://forgejo.org/docs/latest/admin/actions/registration/) and [Actions security](https://forgejo.org/docs/latest/admin/actions/security/).
