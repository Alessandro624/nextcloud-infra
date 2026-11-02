#!/usr/bin/env bash
set -euo pipefail
event=success
if ! curl --noproxy '*' -fsS --max-time 10 http://127.0.0.1:13000/api/healthz >/dev/null 2>&1; then
  event=fail
  if [[ -f /run/forgejo-backup-maintenance ]]; then
    stamp=$(cat /run/forgejo-backup-maintenance)
    if [[ $stamp =~ ^[0-9]+$ ]]; then
      age=$(($(date +%s) - stamp))
      if (( age >= 0 && age < 7200 )); then event=success; fi
    fi
  fi
fi
source /etc/forgejo-backup/environment
for path in /srv/forgejo /var/backups/forgejo; do
  free=$(df -B1 --output=avail "$path" | tail -1)
  if (( free < MIN_FREE_GIB * 1024 * 1024 * 1024 )); then event=fail; fi
done
test -f "$LOCAL_REPO/config" || event=fail
timeout 12s python3 /srv/forgejo/scripts/notify.py service "$event"
