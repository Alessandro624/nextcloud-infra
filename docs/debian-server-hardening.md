# Debian server baseline and maintenance

For a dedicated Debian server hosting Nextcloud AIO and Forgejo. Run the OS sections before or after application setup; repeat the application and network checks after deployment. Commands are for Bash on the Debian server unless stated otherwise. Replace example usernames, addresses and paths before running them.

This guide does not install applications or replace their backup procedures. Keep your completed deployment record private, outside tracked files.

## 1. Prepare and inspect

Have console access (physical console or hypervisor console), a working sudo account and a maintenance window. On an existing installation, first verify recent Nextcloud and Forgejo backups and their off-site copies. Let active backups finish before maintenance. Keep credentials, recovery keys and restore instructions outside this server.

```bash
cat /etc/os-release
uname -r
id
sudo -v
ip -br address
ip route
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS
df -h
df -i
systemctl --failed
systemctl list-timers --all
sudo ss -lntup
```

If installed:

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
sudo tailscale status
sudo tailscale serve status
sudo tailscale funnel status
```

Record existing backup schedules and published ports privately. Do not save full environment dumps or configuration containing secrets.

## 2. Stable address, power and physical protection

1. Prefer Ethernet. Reserve its MAC address in the router's DHCP settings; obtain it with `ip link`. Do not change a working remote interface without console access.
2. In BIOS/UEFI, enable restoration of power after AC loss if appropriate. Test during a maintenance window.
3. For a dedicated always-on host, prevent accidental suspension:

   ```bash
   sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
   ```

   Undo only if you intentionally need sleep: `sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target`.
4. Consider a UPS with supported shutdown software. Configure and test graceful shutdown using its vendor/NUT instructions; do not simulate failure by pulling power from a running server.
5. Review disk encryption and physical access before storing business data. Encryption at rest requires an unlock and recovery plan. Do not attempt an in-place encryption conversion using this checklist.

For a VM, configure autostart and power/disk monitoring on the hypervisor too. Skip laptop-specific Wi-Fi, lid and battery tweaks.

## 3. SSH keys and host access

These settings affect host OpenSSH, not Forgejo's Git SSH service. If you use Tailscale SSH, review its separate access policy as well; an OpenSSH login test must actually use OpenSSH.

On your client, use an existing suitable key or create a new one without overwriting an existing key. Set a passphrase:

```bash
ssh-keygen -t ed25519 -a 64
```

On a Linux/macOS client, copy the public key:

```bash
ssh-copy-id ADMIN_USER@SERVER_ADDRESS
```

On Windows PowerShell, if the default key path was used:

```powershell
Get-Content "$HOME/.ssh/id_ed25519.pub" | ssh ADMIN_USER@SERVER_ADDRESS 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys'
```

On the server, as that administrator:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
sudo -v
sudo /usr/sbin/sshd -T | grep -E '^(pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication|permitrootlogin) '
```

Keep this session open. In a second client terminal, verify key-only login and sudo:

```bash
ssh -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no ADMIN_USER@SERVER_ADDRESS
sudo -v
```

Only after this succeeds, inspect existing settings and includes:

```bash
sudo grep -RniE 'Include|Match|PasswordAuthentication|KbdInteractiveAuthentication|PermitRootLogin|PubkeyAuthentication' /etc/ssh/sshd_config /etc/ssh/sshd_config.d
sudo install -d -m 755 /etc/ssh/sshd_config.d
sudoedit /etc/ssh/sshd_config.d/00-local-hardening.conf
```

Add these settings, preserving any intentional configuration already in that file:

```text
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
```

Do not disable keyboard-interactive authentication if your planned OpenSSH MFA depends on it. OpenSSH normally uses the first obtained setting; confirm that the main file includes the drop-ins and no earlier setting overrides them. Check applicable `Match` blocks with `sshd -T -C user=...,host=...,addr=...` using the real connection details.

```bash
sudo /usr/sbin/sshd -t
sudo /usr/sbin/sshd -T | grep -E '^(pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication|permitrootlogin) '
# Run only if validation succeeds and effective settings are correct:
sudo systemctl reload ssh
```

Test another new key-only login and sudo before closing the original session. If it fails, restore the previous settings from the open session/console, validate and reload again.

## 4. Debian security updates

Run package changes outside backup windows: upgrades may restart services, including Docker, even without rebooting. On an existing server, inspect pending changes first:

```bash
sudo apt update
apt list --upgradable
sudo apt install unattended-upgrades apt-listchanges smartmontools lm-sensors
sudo dpkg-reconfigure -plow unattended-upgrades
sudoedit /etc/apt/apt.conf.d/50unattended-upgrades
```

Review allowed origins against your installed Debian release. Keep the intended Debian security origins; do not enable every third-party origin. Add or merge a local override:

```bash
sudoedit /etc/apt/apt.conf.d/52local-unattended-upgrades
```

```text
Unattended-Upgrade::Automatic-Reboot "false";
```

Verify the effective configuration and the proposed upgrades:

```bash
apt-config dump | grep -E 'APT::Periodic|Unattended-Upgrade::'
systemctl list-timers 'apt-*'
sudo unattended-upgrade --dry-run --debug
sudo tail -n 50 /var/log/unattended-upgrades/unattended-upgrades.log
```

Confirm periodic package-list updates and unattended upgrades are enabled, and review the dry-run origins. Do not treat an active service alone as proof that updates will install.

Security updates may still restart application dependencies. If uninterrupted maintenance windows are mandatory, use scheduled, supervised updates instead and document who applies them. Never leave updates unattended administratively.

Plan kernel reboots separately. A `/var/run/reboot-required` file, when present, is useful but its absence does not prove that no reboot is needed. Review upgrade logs and running kernel after maintenance. Apt does not update container images: follow the separate AIO and Forgejo backup/update/rollback procedures.

## 5. Disk health and temperatures

```bash
sudo smartctl --scan-open
sensors
```

Use the actual device and any `-d` option reported by the scan. Example for a SATA disk only:

```bash
sudo smartctl -a /dev/sda
sudo smartctl -t short /dev/sda
# Wait for the completion time printed above, then:
sudo smartctl -l selftest /dev/sda
```

For NVMe, review `smartctl -a /dev/nvme0` using the actual controller name. Hardware RAID may need controller-specific access; virtual disks usually cannot report physical health. Monitor physical storage on the host in those cases.

Review self-test failures, media errors, wear, spare capacity and trends. SMART PASS does not guarantee a healthy disk. Compare temperatures with the manufacturer's limits; do not use a universal idle-temperature threshold. Schedule long tests outside backup and heavy I/O windows.

Enable continuous monitoring after reviewing its device selection:

```bash
sudoedit /etc/smartd.conf
sudo systemctl enable --now smartmontools.service
sudo systemctl restart smartmontools.service
sudo systemctl status smartmontools.service --no-pager
sudo journalctl -u smartmontools.service -n 50 --no-pager
```

Logs alone are not an alert delivery channel. Configure `smartd` notification routing using `man smartd.conf` (`-m`, or a dedicated `-M exec` handler). Existing Nextcloud Telegram automation does not automatically forward SMART alerts. With a configured recipient/handler, temporarily add `-M test` to the relevant device directive, restart smartd, verify actual delivery, then remove `-M test` and restart. Do not mark disk alerts complete until this test passes. Keep tokens in protected files and send only a short status, not raw disk reports.

## 6. Time, log retention and capacity

```bash
timedatectl status
sudo timedatectl set-timezone Europe/Rome
systemctl status systemd-timesyncd chrony --no-pager
```

Use one time synchronization service. If an existing service is synchronized, keep it. If none is configured, install and enable Debian's systemd-timesyncd:

```bash
sudo apt install systemd-timesyncd
sudo systemctl enable --now systemd-timesyncd
timedatectl timesync-status
```

Review removal proposals before installing if another time service exists. Permit only the chosen resolver/time sources in the network policy. Changing the OS timezone does not change timezone settings explicitly configured in backup software.

Bound journal growth. These are example budgets; increase them if needed for useful incident history and available disk space:

```bash
sudo install -d -m 755 /etc/systemd/journald.conf.d
sudoedit /etc/systemd/journald.conf.d/60-local-limits.conf
```

```ini
[Journal]
Storage=persistent
SystemMaxUse=500M
SystemKeepFree=1G
MaxRetentionSec=30day
```

```bash
sudo systemctl restart systemd-journald
sudo journalctl --flush
journalctl --disk-usage
df -h
df -i
```

Size limits can remove old journal entries; export required incident evidence first. These settings do not cap application files or all Docker logs. For Docker:

```bash
sudo docker info --format '{{.LoggingDriver}}'
sudo docker ps -aq | xargs -r sudo docker inspect --format '{{.Name}} {{json .HostConfig.LogConfig}}'
```

For a Compose service you manage, merge a bounded logging policy into that service, for example:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

It takes effect on container recreation, not a simple restart; schedule this through the application's normal maintenance procedure. Do not manually recreate AIO-managed containers. Follow AIO's supported configuration and inspect their effective logging policy. Do not overwrite Docker's daemon configuration or prune volumes to reclaim space.

Monitor each filesystem holding application data, Docker data and backups, plus inode usage. Set alerts early enough for a complete backup/export cycle; the existing Nextcloud export-space threshold is not a monitor for every filesystem.

## 7. Network and Tailscale review

Before deployment, prepare the policy; after deployment, validate actual host and container traffic using [network isolation](../docs/network.md). That document is a policy and acceptance checklist, not a firewall installation procedure. Start with [Debian network preparation](debian-network-preparation.md); enforcement remains pending until rules have been prepared for the actual host, applied and tested. Do not apply a generic UFW reset or outbound deny remotely.

1. Keep a console and a tested rollback for firewall changes. Review existing rules with `sudo nft list ruleset`, and `sudo iptables-save` / `sudo ip6tables-save` where those tools/backends are used. If UFW is installed, inspect `sudo ufw status verbose` too.
2. Give each person their own Tailscale identity. Require account MFA and restrict grants/ACLs: application users need app ports, administrators alone need host SSH. A default permissive tailnet policy does not provide this separation.
3. Preserve existing Serve routes. Do not run `tailscale serve reset`. Confirm Funnel is unused. Review server key expiry/tag ownership and recovery access deliberately.
4. Check loopback bindings for app backends and admin interfaces. Typical current guides use Nextcloud backend `127.0.0.1:11000`, AIO administration `127.0.0.1:18080`, Forgejo web `127.0.0.1:13000` and Git SSH backend `127.0.0.1:12222`. Use your actual configuration as the source of truth.
5. Validate user-facing Serve ports: typically Nextcloud HTTPS 443, Forgejo HTTPS 8443 and Forgejo Git SSH 2222. Host SSH 22 is a separate administrative permission. Review optional AIO container ports as well.
6. Allow required DNS, time, Tailscale, backup storage and configured monitoring flows. Permit OS/container/application updates during reviewed maintenance windows. Include Forgejo mail, webhooks, mirrors and Actions only when enabled; runners belong on an isolated machine.
7. Enforce outbound restrictions on both host traffic and container forwarding, including IPv6. UFW INPUT rules and Tailscale membership alone are insufficient. Dynamic provider endpoints require maintained rules; a list of hostnames is not itself enforcement.
8. Test from an authorized client, an unauthorized tailnet client and a LAN client. Verify expected access and denial of administration/backends. Confirm unapproved outbound requests are denied from both host and application networks with matching firewall evidence.

Do not declare isolation complete until the linked network tests pass, including backup uploads, monitoring, updates, Office editing and Forgejo clone/push. Repeat them after changing routing or enabling a public domain.

## 8. Monitoring and backup acceptance

Keep Nextcloud's existing Borg/export/off-site workflow and Forgejo's own consistent backup/off-site workflow. Do not add a generic live database copy or a second competing schedule. Ensure backup windows do not overload the same disks or overlap maintenance.

- Follow [Healthchecks monitoring](../docs/monitoring.md) for Nextcloud and [Forgejo production](forgejo-setup.md) for Forgejo. Verify both missed-backup and service-failure alerts reach you.
- Healthchecks must notify independently when the server cannot send. Test this during planned downtime, allowing the configured grace period to expire.
- Test an external-copy restore of each application on an isolated VM. Never restore over production for a drill. Disable outbound jobs, bot polling and production heartbeat URLs on the restored test system.
- Monitor disk space/inodes and SMART through a separately verified alert route. Do not assume application heartbeats cover these additional checks.
- Optionally run Uptime Kuma on the separate laptop, using Tailscale to check both HTTPS endpoints and notify on failure. Restrict it to the required ports; it needs no Docker socket on this server. On the same LAN/power supply it cannot replace external Healthchecks. Do not disable certificate validation to make checks pass.

## 9. Controlled reboot and final checks

Do this after the application setup is complete. Notify users, finish active backups, verify their off-site results and confirm recovery credentials are available. Check service enablement and container restart policies:

```bash
systemctl is-enabled docker tailscaled
systemctl list-timers --all
sudo docker ps -aq | xargs -r sudo docker inspect --format '{{.Name}} {{.HostConfig.RestartPolicy.Name}}'
```

Check the actual automation unit names from your installation (including `nextcloud-automation` and Forgejo backup/monitor timers). Correct missing startup configuration through their setup guides. Then reboot with console access available:

```bash
sudo systemctl reboot
```

Reconnect and inspect:

```bash
uptime
uname -r
systemctl --failed
timedatectl status
df -h
df -i
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
sudo tailscale status
sudo tailscale serve status
sudo ss -lntup
sudo journalctl -b -p err --no-pager
```

Verify Nextcloud login/upload/download/collaborative editing and Forgejo login/clone/push with a disposable test repository. Check monitoring recovery, scheduled jobs and off-site access. Observe the next scheduled backup of each service; a successful boot does not verify backups.

## 10. Routine checklist

Monthly, and after significant changes:

- Review security updates, pending restarts and deployed container versions.
- Review failed services, SMART errors, temperatures, free space and inodes.
- Verify recent local/off-site backup results and alert delivery.
- Review accounts, SSH keys, Tailscale permissions and exposed ports.
- Check log retention and certificate/HTTPS health.
- Repeat an isolated restore at least quarterly and after backup changes.

Keep a private dated record of results and unresolved items. Never mark skipped checks as passed. Before application installation, leave sections 7–9's application-dependent checks pending and complete them afterwards.

## References

- [Debian periodic updates](https://wiki.debian.org/PeriodicUpdates)
- [OpenSSH server configuration](https://man.openbsd.org/sshd_config)
- [Docker firewall behavior](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
- [Docker log rotation](https://docs.docker.com/engine/logging/drivers/json-file/)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [systemd journal configuration](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html)
- Installed Debian references: `man smartd.conf`, `man smartctl`, `man sshd_config`.
