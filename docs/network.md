# Network isolation

Target: deny unapproved outbound traffic and public inbound traffic. This repository does **not** install firewall rules. Compose bindings and application allowlists are not network enforcement. Apply policy on the dedicated host/VM or its gateway, then validate both host and container traffic, IPv4 and IPv6.

## Allowed flows

| Source | Destination / purpose | When |
|---|---|---|
| Authorized tailnet devices | Nextcloud HTTPS through Tailscale Serve | Normal use |
| Local administrator | AIO `127.0.0.1:18080` | Administration |
| Host Tailscale Serve | Apache `127.0.0.1:11000` | Normal use |
| AIO containers | Required peers on the AIO Docker network | Normal use |
| Host and containers | Approved DNS resolver; host to approved time source | Normal use |
| Host Tailscale | Coordination, certificate provisioning, authorized peers and selected DERP/STUN infrastructure | Normal use |
| Automation | `api.telegram.org:443` | Only if Telegram enabled |
| Automation | `hc-ping.com:443` or exact configured monitor hostname | Only if Healthchecks enabled |
| Host rclone | Selected storage API, authentication and transfer endpoints | Backup/verification/retention |
| Docker daemon, OS and AIO | Approved registries, package repositories and application download endpoints | Installation and maintenance |

For Drive, inventory the actual Google API/OAuth/download endpoints used by your rclone version; allowing the browser domain `drive.google.com` alone is insufficient. Do not broadly allow every Google domain. Registry downloads can use separate CDN/storage hosts. Tailscale peers and relay addresses can change: use its current firewall guidance rather than a copied list of static IPs.

Review optional apps before adding exceptions: Talk/STUN, mobile push, federation, external storage, mail, antivirus signatures, external Office/AI integrations and connectivity/update checks can cause additional traffic. Disable unused integrations. Inspect the installed Nextcloud settings `connectivity_check_domains`, `appstoreenabled`, `updatechecker` and `has_internet_connection`; these are application settings, not a firewall. Keep an explicit maintenance process for updates.

## Inventory without exposing secrets

Run on the test host; save any output under ignored `backup/security/` if needed. Do not publish full `docker inspect`, environment dumps or private application configuration.

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
docker network ls
docker inspect --format '{{json .NetworkSettings.Ports}}' nextcloud-aio-mastercontainer
tailscale serve status
tailscale funnel status
```

Funnel should not be configured. On Windows, use `Get-NetTCPConnection` and `Get-NetUDPEndpoint` for host sockets. On Linux, use `sudo ss -lntup` and `sudo ss -ntup`. These snapshots can miss short connections and do not prove container isolation.

At the host/gateway, record firewall connection and DNS logs during startup, 30 minutes idle, login/sharing, simultaneous Office editing, a full backup, monitoring and a maintenance update. Correlate source process/container, destination, port and purpose. Keep capture/log files private. Browser/mobile traffic must be tested separately from server traffic.

## Enforce and validate

1. Use a disposable deployment and keep console access plus a firewall rollback available. Prefer a dedicated server/VM and gateway rules over changing a shared desktop's global policy.
2. Permit necessary internal flows first. Restrict tailnet access to intended users and Nextcloud's required ports; do not grant the entire LAN or administrative ports by default.
3. Add only reviewed outbound destinations. Enforce on the host **and** Docker forwarding path, or at a gateway covering both. Handle IPv6 explicitly. With Docker Desktop, account for the VM/backend traffic.
4. Deny other outbound connections and log denials. Do not allow arbitrary DNS, DNS-over-HTTPS, proxies, VPN exit nodes or alternate routes to bypass policy. The Python monitor and Telegram client ignore ambient proxy settings; Docker/rclone/OS settings must be reviewed separately.
5. From both the host and an AIO container, try an unapproved destination. For example, if `example.com` is deliberately outside the allowlist:

   ```bash
   curl --connect-timeout 5 --max-time 10 https://example.com/
   docker exec nextcloud-aio-nextcloud curl --connect-timeout 5 --max-time 10 https://example.com/
   ```

   Require a matching firewall denial, not merely a failed command. Repeat with direct IPv4/IPv6 addresses of a controlled test endpoint to rule out DNS-only blocking. Use a preinstalled test client if curl is unavailable; do not download a helper while testing isolation.
6. Repeat the functional tests and [monitoring failure tests](monitoring.md). Verify an unauthorized tailnet device and a LAN device cannot reach administration or the backend. Check all optional AIO container ports, not only Compose ports.
7. Close the maintenance exceptions and repeat the negative test. Record OS, Docker/AIO versions, rules, observed endpoints, evidence and date in a private deployment record.

Do not declare isolation validated until these tests pass. Docker's firewall integration varies by backend; host INPUT/UFW rules alone may not cover published ports or container forwarding. Future public-domain access requires a new review of inbound HTTPS, certificates and proxy trust.

References: [Docker firewall behavior](https://docs.docker.com/engine/network/packet-filtering-firewalls/), [Tailscale firewall requirements](https://tailscale.com/docs/integrations/firewalls), [Nextcloud settings](https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/config_sample_php_parameters.html), [rclone Drive](https://rclone.org/drive/).
