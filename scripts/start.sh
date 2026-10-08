#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then cp .env.example .env; fi
docker compose -f compose.yml config --quiet
python3 scripts/backup.py prepare
docker compose -f compose.yml up -d
echo 'AIO administration binding (open the published host port using HTTPS):'
docker compose -f compose.yml port nextcloud-aio-mastercontainer 8080
echo 'Run bash scripts/tailscale.sh, then enter its HTTPS hostname in the AIO wizard.'
