# Debian outbound isolation worksheet

Deployment procedure. Scope: Nextcloud AIO, standalone Forgejo, their two bots, MEGA off-site copies and Healthchecks. This server neither uses nor provides a Tailscale exit node/subnet router.

Status: this guide prepares evidence and acceptance criteria. It does not install outbound enforcement. Preserve working rules and console access.

## 1. Refresh the evidence

Collect current evidence after all chosen services and DNS/startup fixes are working. An observed IP is not automatically an approved destination.

Copy the read-only collector from the laptop repository:

```powershell
scp modules/network/collect.py SSH_HOST:~/collect-network.py
```

Replace `SSH_HOST` with your existing SSH alias. On Debian:

```bash
OUT="$HOME/network-audit-$(date +%Y%m%d-%H%M%S)"
sudo python3 "$HOME/collect-network.py" --duration 1800 --output "$OUT"
```

The output directory must not exist; its parent must exist. Files are private and owned by the invoking sudo user. Optional missing tools are recorded, not installed. The collector makes no firewall, service, DNS or routing changes. Each event collector is capped at 16 MiB; inspect `collection.json` and collector errors before trusting coverage.

During collection, use the laptop/phone for UI activity, not a browser on the server:

1. Leave the services idle for five minutes.
2. Open homepage, Nextcloud and Office; edit collaboratively and upload/download a test file.
3. Clone/push a test Forgejo repository; test LFS/packages only if used.
4. Send status commands to both bots and observe a Healthchecks heartbeat.
5. Observe a complete Nextcloud off-site transfer and Forgejo off-site transfer, separately. Do not bypass manual quotas or launch overlapping jobs for the audit. Capture scheduled runs separately if needed.

Record activity times in a small `activities.txt` alongside the files. If thirty minutes is insufficient, start a new collection with a new output directory, up to 7200 seconds. Do not artificially restart Docker or Tailscale during collection.

The DNS capture stores textual DNS query/response metadata, not a raw packet capture. It may include private names. Firewall/socket output contains IPs and process names. Keep it private; review before sharing. Encrypted DNS and Tailscale-internal traffic may not appear. Socket snapshots can miss short-lived processes. A `NEW`/`UNREPLIED` conntrack event alone does not prove a blocked connection.

Download from the laptop using the exact generated directory name:

```powershell
scp -r SSH_HOST:~/network-audit-YYYYMMDD-HHMMSS backup/
```

If tools such as tcpdump or conntrack are unavailable, review the available snapshot and `collection.json` locally before deciding whether to install missing tools.

## 2. Review flows before generating rules

| Origin | Required destination | Treatment |
| --- | --- | --- |
| Host | Loopback and the reviewed application backends | Keep local service paths |
| AIO containers | Required AIO peers and server Tailscale HTTPS callback | Keep Office/internal flows; use discovered network identities |
| Forgejo container | Its configured internal dependencies | No general Internet access assumed |
| Host/container DNS | Approved resolvers and MagicDNS path | Verify host-originated vs forwarded queries |
| NetworkManager/time daemon | DHCP, necessary IPv6 control traffic, selected time servers | Keep network bootstrap and renewal |
| Tailscale host process | Coordination, certificates, relays and peer transport | Dynamic endpoints; review separately |
| Both bots | Telegram HTTPS | Same API destination, separate processes/tokens |
| Monitoring | Configured Healthchecks host over HTTPS | Outbound only |
| rclone/restic | MEGA API and actual storage endpoints over HTTPS | Include authentication, transfer, verification and retention |
| OS/Docker/AIO | Approved package/image/application sources | Explicit maintenance policy, not blanket permanent HTTPS |

Classify desktop/browser/discovery traffic separately; do not approve it merely because it appeared in the capture. Keep deployment-specific addresses here, never in reusable tracked docs.

MEGA and Tailscale endpoints change. DNS-to-IP sets need refresh and failure handling; shared IPs are not strict hostname filtering. A firewall that permits all TCP 443 does not satisfy the requested destination restriction. A root UID exception would also include Docker, Forgejo backup and other root processes, not just Tailscale.

## 3. Enforcement gate

After reviewing the new evidence, prepare a separate ruleset for host OUTPUT and forwarded container traffic, for both IPv4 and IPv6. Account for Tailscale rules preceding Docker/UFW; DOCKER-USER alone may not cover every forwarded path. Never flush Docker, UFW or Tailscale rules or switch firewall backend as part of this change.

The deployable bundle must contain:

- Syntax validation and a rollback that removes only its own rules.
- A timed rollback armed and verified before enforcement, with console access.
- Initial observation of would-be denials; no automatic promotion of observed traffic to allow rules.
- Destination refresh/expiry behavior, explicit maintenance exceptions and startup ordering.
- Positive tests: reboot, DNS, both bots, both full backups, Office, Forgejo and homepage.
- Negative tests: controlled disallowed destinations from host and containers, IPv4/IPv6, and unauthorized LAN/tailnet clients. Require a matching firewall counter/log; DNS failure alone is insufficient.

Do not cancel rollback until the live checks pass. Then test persistence separately after reboot. No outbound deny command is provided yet because the destination list and current forwarding order have not been verified.

References: [Tailscale transport requirements](https://tailscale.com/docs/reference/faq/firewall-ports), [Docker firewall behavior](https://docs.docker.com/engine/network/packet-filtering-firewalls/), [Docker nftables and chain priority](https://docs.docker.com/engine/network/firewall-nftables/).
