# Office callbacks through Tailscale Serve

Use on a Linux Docker host only after confirming that Office callbacks fail because UFW blocks the AIO bridge and Serve binds its HTTPS listener to `tailscale0`. Keep console access available. These commands require Bash, Python 3 and an existing AIO network.

## Allow the internal connection

Keep UFW active with default deny incoming, IPv6 filtering enabled, and no broad LAN allowances. Derive the current bridge, IPv4 subnet and server address:

```bash
AIO_ID=$(sudo docker network inspect -f '{{.Id}}' nextcloud-aio)
AIO_BRIDGE=$(sudo docker network inspect -f '{{index .Options "com.docker.network.bridge.name"}}' nextcloud-aio)
if [ -z "$AIO_BRIDGE" ]; then AIO_BRIDGE="br-${AIO_ID:0:12}"; fi
AIO_SUBNET=$(sudo docker network inspect nextcloud-aio | python3 -c 'import sys,json,ipaddress; print(next(x["Subnet"] for x in json.load(sys.stdin)[0]["IPAM"]["Config"] if ipaddress.ip_network(x["Subnet"]).version == 4))')
TAIL_IP=$(tailscale ip -4)
printf 'Bridge=%s Subnet=%s Destination=%s:443\n' "$AIO_BRIDGE" "$AIO_SUBNET" "$TAIL_IP"
```

Stop if any value is empty or unexpected. Then:

```bash
sudo ufw allow in on "$AIO_BRIDGE" from "$AIO_SUBNET" to "$TAIL_IP" port 443 proto tcp
sudo ufw status verbose
```

UFW persists this rule. If Docker recreates the network or the Tailscale address changes, remove the old exact rule and derive a new one. Do not allow all Docker bridges or the entire tailnet address range.

## Persist the tested Serve setting

`TS_SERVE_ALLOW_ALL_INTERFACES` removes the interface restriction for all Serve kernel listeners, including other Serve ports. It does not enable Funnel. Local traffic must be restricted by the host firewall; tailnet access policy alone does not protect this path. This is an internal Tailscale option: revalidate after upgrades.

From the server console (Tailscale connections briefly disconnect):

```bash
sudo mkdir -p /etc/systemd/system/tailscaled.service.d
sudo tee /etc/systemd/system/tailscaled.service.d/90-aio-office.conf >/dev/null <<'EOF'
[Service]
Environment="TS_SERVE_ALLOW_ALL_INTERFACES=true"
EOF
sudo rm -f /run/systemd/system/tailscaled.service.d/90-aio-test.conf
sudo systemctl daemon-reload
sudo systemctl restart tailscaled
sudo systemctl show tailscaled --property=Environment
sudo ss -lntp 'sport = :443'
```

Expect the option to be `true` and no `%tailscale0` suffix on the Serve listener.

## Validate before accepting

Set the actual Nextcloud hostname, without a scheme or path:

```bash
NC_HOST='REPLACE_WITH_NEXTCLOUD_HOSTNAME'
sudo docker exec nextcloud-aio-nextcloud curl --fail --show-error \
  --connect-timeout 5 --max-time 15 "https://$NC_HOST/status.php"
```

- Require HTTP success and `installed: true`; test Office opening, saving and simultaneous editing from two clients.
- Check `tailscale serve status` and `tailscale funnel status`; Funnel must remain disabled.
- From an unauthorized tailnet identity, verify application and administrative access is denied by policy.
- From a separate LAN device, test LAN IPv4/IPv6 and, where a route exists, the server's Tailscale IP over the LAN. Test all Serve ports (including Forgejo 8443/2222 if configured) and backends 11000/18080/13000/12222. Require firewall evidence of denial; a missing route is not proof of filtering. Do not add LAN routes on the production host merely for this test.
- Review Docker port publishing separately: host UFW INPUT rules do not cover every forwarding path.
- Reboot with console access and repeat the positive and negative tests. Record results privately; successful Office editing alone does not establish isolation.

## Roll back

Office callbacks will fail again if they require this exception:

```bash
sudo rm /etc/systemd/system/tailscaled.service.d/90-aio-office.conf
sudo systemctl daemon-reload
sudo systemctl restart tailscaled
# Reuse the reviewed values above, or identify the exact rule with ufw status numbered.
sudo ufw delete allow in on "$AIO_BRIDGE" from "$AIO_SUBNET" to "$TAIL_IP" port 443 proto tcp
```

Reference: [Tailscale 1.104.2 Serve implementation](https://github.com/tailscale/tailscale/blob/v1.104.2/ipn/ipnlocal/serve.go).
