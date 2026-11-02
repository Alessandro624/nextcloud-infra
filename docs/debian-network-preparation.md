# Debian network preparation

Deployment worksheet; keep completed inventories private. Target: firewall on the Debian host running Docker and Tailscale. These commands only inspect configuration. They do not implement isolation.

## 1. Recovery prerequisites

Record whether this is a physical machine or VM and how you can access its console if SSH fails. Record whether the current shell uses LAN SSH, OpenSSH over Tailscale, Tailscale SSH or the console. Do not start enforcement without working console access and a timed rollback plan.

## 2. Collect the current configuration

Run these on Debian, not on the Windows client. Missing optional commands should be reported as missing; do not install or switch firewall managers yet.

```bash
cat /etc/os-release
sudo docker version --format 'Docker server: {{.Server.Version}}'
sudo docker info --format '{{json .SecurityOptions}}'
sudo docker info | grep -i -E 'firewall|rootless|swarm'
ip -br address
ip -4 route
ip -6 route
readlink -f /etc/resolv.conf
cat /etc/resolv.conf
sudo ss -lntup
sudo docker ps --format 'table {{.Names}}\t{{.Ports}}'
sudo docker network ls
sudo tailscale version
sudo tailscale serve status
sudo tailscale funnel status
```

Inspect each installed firewall tool; absence is useful information:

```bash
if command -v nft >/dev/null; then sudo nft list ruleset; fi
if command -v iptables >/dev/null; then sudo iptables --version; sudo iptables-save; fi
if command -v ip6tables >/dev/null; then sudo ip6tables-save; fi
if command -v ufw >/dev/null; then sudo ufw status verbose; fi
systemctl is-active nftables ufw firewalld
```

If Docker's backend is not printed, inspect its startup options and `/etc/docker/daemon.json` locally for `firewall-backend`, `iptables`, `ip6tables` and `ipv6`. Do not publish the whole file or service environment. An `iptables --version` containing `nf_tables` identifies the iptables compatibility layer; it does not by itself mean Docker uses its native nftables backend.

These outputs include network addresses and hostnames. Keep the full originals private; when sharing, redact public addresses or names consistently while retaining interfaces, subnet relationships, ports, chains and rule order. Never include tokens, environment dumps or full application configuration.

## 3. Information needed for the rule set

- Console availability and current administrative access path.
- Current DNS and time services; DHCP or fixed network configuration.
- Enabled Nextcloud optional services and actual Forgejo ports.
- Whether this host is a Tailscale exit node/subnet router, or uses one.
- Backup provider and enabled Telegram/Healthchecks/mail/webhook/mirror integrations.
- Existing firewall ownership and Docker backend from section 2.

Do not assume Nextcloud and Forgejo need the same outbound permissions. Record runtime destinations separately from maintenance downloads. DNS-resolved IP allowlists are not strict domain filtering: shared CDN IPs can serve other domains, and addresses change.

## 4. Implementation and acceptance gates

After reviewing the inventory, prepare a host-specific ruleset covering INPUT, OUTPUT and Docker forwarding for IPv4 and IPv6. Preserve Docker and Tailscale's own rules. Include DHCP/IPv6 control traffic where required, approved DNS/time, application peers, administration, Tailscale transport and the reviewed external services.

The implementation must include syntax validation, a timed rollback limited to its own changes, initial observation logs, controlled enforcement, reboot persistence, and a way to open and close maintenance exceptions. Do not run `nft flush ruleset`, blindly restore stale Docker rules, or enable a blanket outbound deny as a shortcut.

Only then run [network acceptance tests](../docs/network.md#enforce-and-validate), including authorized and unauthorized clients, host and container egress, IPv6, full backup/upload, monitoring, Office editing and Forgejo clone/push. Record actual denials. Repeat after reboot and after closing maintenance exceptions.

## 5. First deployment stage: host ingress

Prerequisites: Debian with Docker using the iptables backend, UFW currently inactive, Nextcloud backend/admin bound to loopback, working SSH over Tailscale with keys and tested console access. Verify these against your own inventory before proceeding. This example covers Nextcloud only; account for additional services separately. An active UFW systemd unit does not prove filtering is enabled.

This stage limits ordinary host ingress from the LAN. It deliberately leaves outbound traffic allowed while required destinations are established. It is not the final network isolation policy and does not enforce Docker forwarding or tailnet identity permissions.

### Review saved UFW configuration

Run on Debian. Keep the current SSH session and console available:

```bash
sudo /usr/sbin/ufw show added
sudo grep '^IPV6=' /etc/default/ufw
```

Require `IPV6=yes` for both address families. If disabled, edit `/etc/default/ufw` with `sudoedit` before continuing. Review any saved allow rules: a default deny does not override explicit allowances. Remove unwanted rules individually, using the corresponding `ufw delete ...` command; do not reset the entire ruleset. Do not continue with unexplained broad allows.

Save configuration privately for reference (not for automatic restoration of stale Docker rules):

```bash
sudo sh -c 'umask 077; tar -czf "/root/ufw-before-$(date +%Y%m%d-%H%M%S).tgz" /etc/ufw /etc/default/ufw'
```

### Configure and arm rollback

These rules permit host SSH and HTTPS through Tailscale and the encrypted Tailscale UDP transport:

```bash
sudo /usr/sbin/ufw default deny incoming
sudo /usr/sbin/ufw default allow outgoing
sudo /usr/sbin/ufw allow in on tailscale0 to any port 22 proto tcp
sudo /usr/sbin/ufw allow in on tailscale0 to any port 443 proto tcp
# Only when the Forgejo module is installed:
# sudo /usr/sbin/ufw allow in on tailscale0 to any port 8443 proto tcp
# sudo /usr/sbin/ufw allow in on tailscale0 to any port 2222 proto tcp
sudo /usr/sbin/ufw allow 41641/udp
sudo /usr/sbin/ufw logging low
sudo systemd-run --unit=nextcloud-ufw-rollback --on-active=10m /usr/sbin/ufw disable
sudo systemctl status nextcloud-ufw-rollback.timer --no-pager
```

Continue only if the rollback timer is waiting. It disables UFW after ten minutes, returning to the original inactive state; it does not remove the saved configuration. Then enable filtering:

```bash
sudo /usr/sbin/ufw enable
sudo /usr/sbin/ufw status verbose
```

### Test before cancelling rollback

1. From a second laptop terminal, open a **new** SSH session through the server's Tailscale hostname and verify `sudo -v`. The existing session alone is not a valid test.
2. Follow [Office callbacks through Tailscale Serve](../docs/tailscale-office.md) if the container callback is blocked. Open Nextcloud through its Tailscale HTTPS URL. Upload/download a test file and verify Office editing.
3. From the LAN, test the server's LAN address: SSH 22 and backends 11000/18080 should be blocked. Ensure the client actually has a route to that LAN; a timeout caused by client isolation is not proof of the host firewall. Correlate with `sudo journalctl -k --since '10 minutes ago'` and UFW rule counters.
4. Verify `sudo tailscale status`, DNS and the normal monitoring/backup connections remain functional.

After successful tests, while the timer is still waiting:

```bash
sudo systemctl stop nextcloud-ufw-rollback.timer
sudo /usr/sbin/ufw status verbose
```

Require `Status: active`. If rollback already ran, do not assume protection is enabled: investigate, schedule another rollback and repeat enablement/tests. If anything breaks, allow the timer to run or use `sudo /usr/sbin/ufw disable` from the console. Do not reboot during the timed test: the transient rollback timer does not survive reboot. After acceptance, perform a separate controlled reboot with console access and repeat the checks.

### Limits and next stage

Tailscale's existing `ts-input` chain accepts tailnet ingress and may run before UFW. The two UFW port rules therefore do **not** prove that other ports are blocked inside the tailnet. Restrict users and ports in the Tailscale access policy and test an unauthorized identity. Docker-published ports also require separate forwarding controls; preserve loopback bindings meanwhile.

Next, observe runtime, backup and maintenance destinations and implement the reviewed outbound policy on host OUTPUT and Docker forwarding, accounting for Tailscale's earlier forwarding accepts. Do not set `ufw default deny outgoing` as a shortcut. Dynamic cloud endpoints and Tailscale transport require maintained exceptions. Desktop services, if installed (such as KDE Connect, Avahi and CUPS) should be disabled separately if unused; this stage does not stop their outbound traffic.

References: [Tailscale netfilter modes](https://tailscale.com/docs/reference/netfilter-modes), [Docker and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

Record your own status: inventory reviewed, ingress tested, outbound rules implemented, and isolation validated. These instructions do not establish that any check has passed on your host.

Next stage: follow the [outbound isolation worksheet](debian-egress-hardening.md) to refresh evidence before generating enforcement rules. Keep its results private.
