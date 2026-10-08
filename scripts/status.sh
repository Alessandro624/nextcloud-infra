#!/usr/bin/env bash
set -euo pipefail
docker info --format '{{.OSType}}'
docker ps -a --filter name=nextcloud-aio --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
df -h
echo 'Container status only. Verify application health and backups through AIO.'
