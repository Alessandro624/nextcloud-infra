#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f compose.yml config --quiet
docker compose -f compose.yml up -d
echo 'AIO administration: https://localhost:8080 (unless the host port was changed).'
echo 'Configure the domain and manage application containers through AIO.'
