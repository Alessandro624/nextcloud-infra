# Private workspace homepage

A static page at `https://home.YOUR_TAILNET.ts.net`. Nextcloud keeps its existing HTTPS 443 address; Forgejo keeps HTTPS 8443 and Git SSH 2222. No application hostname or port migration is needed. Nextcloud AIO does not support an external HTTPS port other than 443.

Use `modules/homepage` from the trusted checkout on the server. No secrets belong in this page. Its links do not grant access to the applications.

## 1. Prepare the page

From the repository root on the Debian server, substitute the real existing URLs:

```bash
mkdir -p backup
python3 modules/homepage/render.py \
  --nextcloud https://SERVER.YOUR_TAILNET.ts.net \
  --forgejo https://SERVER.YOUR_TAILNET.ts.net:8443 \
  --output backup/homepage.html
sudo install -d -m 755 /srv/workspace-home
sudo install -m 644 backup/homepage.html /srv/workspace-home/index.html
```

The renderer refuses to overwrite an existing output. For updates, render to a new filename, review it, then install it. Edit the template to change the title, descriptions or colors. The page contains no scripts, fonts loaded from the Internet, analytics or status polling.

For Nextcloud only, omit `--forgejo`. Omit Forgejo ports from the policy below and skip its acceptance checks if that module is not installed.

## 2. Prepare Tailscale access

Use a current Tailscale client (1.94+ on clients avoids the older Linux route opt-in). Services require a tagged host and administrative console access. Keep console recovery available when changing the server identity.

Before assigning a tag, merge this example into the existing tailnet policy, replacing emails with actual members. Do not replace the whole policy:

```json
{
  "groups": {
    "group:workspace-admins": ["ADMIN@example.com"],
    "group:workspace-users": ["ADMIN@example.com", "MEMBER@example.com"]
  },
  "tagOwners": {
    "tag:workspace-server": ["group:workspace-admins"]
  },
  "grants": [
    {"src": ["group:workspace-admins"], "dst": ["tag:workspace-server"], "ip": ["tcp:22"]},
    {"src": ["group:workspace-users"], "dst": ["tag:workspace-server"], "ip": ["tcp:443", "tcp:8443", "tcp:2222"]}
  ]
}
```

Preserve any separately required host outbound permissions: tagging replaces the device's user identity. Review rules using user identity or `autogroup:self`, including host-to-host traffic. This example assumes ordinary OpenSSH with keys; Tailscale SSH needs its own policy. Broad existing allows remain effective until removed; narrow grants do not override them.

In Machines, assign `tag:workspace-server` to this server. Immediately test a **new** SSH session, both apps, Office editing and Git push. If access changes unexpectedly, use the console and correct the policy before continuing. Do not log out or re-enroll the node as a troubleshooting shortcut.

## 3. Publish only the homepage

In the console's Services section, define `home` with endpoint `tcp:443`. Add this entry to the policy's existing `grants` list:

```json
{"src": ["group:workspace-users"], "dst": ["svc:home"], "ip": ["tcp:443"]}
```

Check that `home` is unused. Save the current Serve configuration privately, then publish only this file:

```bash
sudo tailscale serve status
sudo tailscale serve --service=svc:home --https=443 /srv/workspace-home/index.html
sudo tailscale serve status
sudo tailscale funnel status
```

Approve this host's advertisement for `home` in the console. Use the HTTPS address printed by Tailscale. Do not enable Funnel or reset Serve. The service uses its own virtual address, so its 443 does not replace Nextcloud's 443. Only the HTML file is served, not the repository or backup directory.

## 4. Verify and retain

- On laptop and phone, open the homepage, then follow both links and sign in.
- Check Nextcloud upload/download/Office and Forgejo clone/push still work.
- Test a tailnet identity outside the permitted groups: it must be denied. Remove conflicting broad policy grants only after reviewing all required access.
- Check from outside Tailscale: the page must not be publicly accessible.
- Reboot during maintenance and verify all three sites and SSH again.
- Save the template, renderer, generated HTML and relevant tailnet policy in the private recovery kit. Neither application's existing backup automatically includes `/srv/workspace-home`.

The homepage is not a health monitor. Existing service/backup monitoring remains necessary. Add a separate availability check if desired, without exposing an administrative dashboard to ordinary users.

## 5. Roll back the homepage

```bash
sudo tailscale serve drain svc:home
# Once homepage connections are idle:
sudo tailscale serve --service=svc:home --https=443 off
sudo tailscale serve status
```

Remove only the `svc:home` grant and Service definition if retiring it. Keep the server tag and application grants while they are in use. Do not run a global reset. Keep the local files for recovery.

## Next: outbound isolation

After these checks, collect the current firewall inventory from [network preparation](debian-network-preparation.md). Observe Nextcloud, Forgejo, both backups, MEGA transfers, Telegram, Healthchecks and maintenance traffic before preparing outbound rules. Homepage deployment and tailnet permissions do not implement host/container egress filtering.

References: [Tailscale Services](https://tailscale.com/docs/features/tailscale-services), [Tailscale grants](https://tailscale.com/docs/features/grants), [Nextcloud AIO port requirement](https://github.com/nextcloud/all-in-one#are-other-ports-than-the-default-443-for-nextcloud-supported).
