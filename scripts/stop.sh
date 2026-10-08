#!/usr/bin/env bash
set -euo pipefail
echo 'Stop application containers through AIO before stopping the master.'
read -r -p 'Application containers stopped? Type STOP to continue: ' answer
[[ "$answer" == STOP ]] || exit 1
cd "$(dirname "$0")/.."
docker compose -f compose.yml stop
