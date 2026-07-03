#!/usr/bin/env bash
# BugHuntyBumpy - Linux-Deploy Schritt 2: Build + Start Kern-Stack + Airgap.
# Idempotent. Baut Runner-Image (build-only-Profil), startet Kern-Dienste,
# wartet Health, aktiviert Sandbox-Egress-Block (host-firewall.sh).
# Aufruf:  sudo deploy/02_deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

log() { printf '[deploy] %s\n' "$*"; }
die() { printf '[deploy] FEHLER: %s\n' "$*" >&2; exit 1; }

CORE="postgres redis traefik pie-web casg-api csve-broker relay-worker"

[ -f "$ROOT/.env" ] || die ".env fehlt. Erst deploy/01_bootstrap.sh."
docker info >/dev/null 2>&1 || die "Docker-Daemon nicht erreichbar."

log "Images bauen (Kern)."
docker compose build $CORE

log "Runner-Image bauen (build-only-Profil) -> bhb/csve-runner:latest."
docker compose --profile build-only build csve-runner

log "Netze + Kern-Stack starten."
docker compose up -d $CORE

# --- Health-Wait: postgres + redis ueber Compose-Health, http ueber curl. ---
wait_healthy() {
  svc="$1"; tries=30
  while [ $tries -gt 0 ]; do
    cid="$(docker compose ps -q "$svc" 2>/dev/null || true)"
    [ -n "$cid" ] || { sleep 2; tries=$((tries-1)); continue; }
    st="$(docker inspect -f '{{ if .State.Health }}{{ .State.Health.Status }}{{ else }}none{{ end }}' "$cid" 2>/dev/null || echo none)"
    case "$st" in
      healthy) log "$svc healthy."; return 0 ;;
      none)    log "$svc ohne Healthcheck (laeuft)."; return 0 ;;
    esac
    sleep 2; tries=$((tries-1))
  done
  die "$svc nicht healthy nach Timeout."
}

wait_healthy postgres
wait_healthy redis

log "HTTP-Health pruefen (traefik -> casg-api)."
tries=30
until curl -fsS http://localhost:6080/api/health >/dev/null 2>&1; do
  tries=$((tries-1)); [ $tries -gt 0 ] || die "casg-api Health nicht erreichbar (Port 6080)."
  sleep 2
done
log "casg-api Health ok."

# --- Sandbox-Airgap (zweite Linie). Netz existiert durch 'compose up'. ---
if [ "$(id -u)" -eq 0 ]; then
  log "host-firewall.sh: Sandbox-Egress-Block."
  bash "$ROOT/host-firewall.sh" || log "WARN: Firewall-Block fehlgeschlagen (Netz noch nicht da?)."
else
  log "WARN: nicht root -> host-firewall.sh uebersprungen. Spaeter: sudo bash host-firewall.sh"
fi

log "Deploy fertig. Formular: http://<host>:6080/"
