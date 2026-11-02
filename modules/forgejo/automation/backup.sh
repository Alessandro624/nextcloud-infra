#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
set -a
source /etc/forgejo-backup/environment
set +a
exec /usr/bin/python3 /srv/forgejo/scripts/backup_recovery.py
