#!/usr/bin/env bash
# BugHuntyBumpy - Linux-Deploy: Abbau. Stoppt Stack. Optional Volumes purge.
# Aufruf:  deploy/03_teardown.sh [--purge]
#   --purge  loescht auch Volumes (pg-data, redis-data, minio-data) - DATENVERLUST.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

log() { printf '[teardown] %s\n' "$*"; }

if [ "${1:-}" = "--purge" ]; then
  log "Stack stoppen + Volumes loeschen (DATENVERLUST)."
  docker compose --profile build-only --profile full --profile scan down -v --remove-orphans
else
  log "Stack stoppen (Volumes bleiben)."
  docker compose --profile build-only --profile full --profile scan down --remove-orphans
fi

log "Abbau fertig."
