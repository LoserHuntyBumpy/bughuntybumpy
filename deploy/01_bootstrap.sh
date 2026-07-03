#!/usr/bin/env bash
# BugHuntyBumpy - Linux-Deploy Schritt 1: .env erzeugen + starke Secrets.
# Verhindert Deploy mit Platzhalter 'change-me-strong' (Audit S7).
# Idempotent: bestehende .env mit echten Secrets bleibt unveraendert.
# Aufruf:  deploy/01_bootstrap.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"
PLACEHOLDER="change-me-strong"

log() { printf '[bootstrap] %s\n' "$*"; }
die() { printf '[bootstrap] FEHLER: %s\n' "$*" >&2; exit 1; }

rand() { openssl rand -base64 24 | tr -d '\n/+=' | cut -c1-32; }

[ -f "$ENV_EXAMPLE" ] || die ".env.example fehlt in $ROOT."

if [ ! -f "$ENV_FILE" ]; then
  log ".env nicht vorhanden -> aus .env.example erzeugen."
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

# Platzhalter durch Random ersetzen. Nur Zeilen mit exakt PLACEHOLDER-Wert.
replace_secret() {
  key="$1"
  if grep -qE "^${key}=${PLACEHOLDER}\$" "$ENV_FILE"; then
    val="$(rand)"
    # In-place: key=PLACEHOLDER -> key=<rand>
    tmp="$(mktemp)"
    sed "s|^${key}=${PLACEHOLDER}\$|${key}=${val}|" "$ENV_FILE" > "$tmp"
    mv "$tmp" "$ENV_FILE"
    log "${key} auf Zufallswert gesetzt."
  fi
}

replace_secret PG_PASSWORD
replace_secret MINIO_SECRET_KEY

# Traefik-Dashboard BasicAuth (F-003): fehlender oder leerer Wert ->
# Hash generieren. $ im apr1-Hash als $$ escapen (compose-Interpolation).
if ! grep -qE '^TRAEFIK_DASHBOARD_AUTH=.' "$ENV_FILE"; then
  dash_pw="$(rand)"
  dash_hash="$(openssl passwd -apr1 "$dash_pw")"
  dash_esc="$(printf '%s' "$dash_hash" | sed 's/\$/$$/g')"
  tmp="$(mktemp)"
  grep -vE '^TRAEFIK_DASHBOARD_AUTH=$' "$ENV_FILE" > "$tmp" || true
  printf 'TRAEFIK_DASHBOARD_AUTH=admin:%s\n' "$dash_esc" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
  log "TRAEFIK_DASHBOARD_AUTH gesetzt. Dashboard-Login admin:${dash_pw} (einmalige Anzeige, sicher ablegen)."
fi

chmod 600 "$ENV_FILE"

# Harter Stopp falls noch Platzhalter uebrig.
if grep -qE "=${PLACEHOLDER}\$" "$ENV_FILE"; then
  die "Restliche '${PLACEHOLDER}'-Werte in .env. Manuell setzen, dann erneut."
fi

log ".env bereit (chmod 600). Secrets gesetzt."
