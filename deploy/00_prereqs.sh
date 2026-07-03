#!/usr/bin/env bash
# BugHuntyBumpy - Linux-Deploy Schritt 0: Voraussetzungen pruefen/installieren.
# Idempotent. Root noetig fuer apt-Install + Firewall.
# Aufruf:  sudo deploy/00_prereqs.sh
set -euo pipefail

log() { printf '[prereqs] %s\n' "$*"; }
die() { printf '[prereqs] FEHLER: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "als root ausfuehren (sudo)."

# --- Docker Engine ---
if ! command -v docker >/dev/null 2>&1; then
  log "Docker nicht gefunden. Installation via get.docker.com."
  curl -fsSL https://get.docker.com | sh
else
  log "Docker vorhanden: $(docker --version)"
fi

# --- Docker Compose v2 (Plugin) ---
if ! docker compose version >/dev/null 2>&1; then
  die "Docker Compose v2 fehlt. Plugin 'docker-compose-plugin' installieren."
fi
log "Compose vorhanden: $(docker compose version | head -n1)"

# --- Hilfswerkzeuge ---
for tool in openssl iptables curl; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool fehlt. Bitte installieren."
done
log "openssl/iptables/curl vorhanden."

# --- Docker-Daemon laeuft ---
docker info >/dev/null 2>&1 || die "Docker-Daemon nicht erreichbar. 'systemctl start docker'."

log "Voraussetzungen erfuellt."
