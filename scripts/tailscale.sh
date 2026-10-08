#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v tailscale >/dev/null || { echo 'Install Tailscale on this host and sign in first.' >&2; exit 1; }
# Compose resolves .env and shell overrides; never execute .env as shell code.
settings=$(docker compose -f compose.yml config --format json)
command -v python3 >/dev/null || { echo 'This helper requires Python 3 to read Compose settings.' >&2; exit 1; }
port=$(printf '%s' "$settings" | python3 -c 'import json,sys; e=json.load(sys.stdin)["services"]["nextcloud-aio-mastercontainer"]["environment"]; assert e["APACHE_IP_BINDING"] == "127.0.0.1", "Host-based Tailscale Serve requires APACHE_IP_BINDING=127.0.0.1"; print(e["APACHE_PORT"])')
tailscale status >/dev/null
tailscale serve --bg "http://127.0.0.1:$port"
tailscale serve status
echo 'Enter the displayed hostname in AIO, without https:// or a path.'
echo 'The backend becomes available after you start the application containers in AIO.'
