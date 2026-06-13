#!/usr/bin/env bash
# Airgap-Verifikation Runner-VM (Plan Phase 4). Laeuft IN der Runner-VM
# (oder als repro-Step). Jeder Egress-Versuch MUSS scheitern. Exit 0 nur,
# wenn kein Pfad nach draussen existiert.
set -u
fail=0

echo "[airgap] ICMP 8.8.8.8 (muss scheitern)"
if ping -c1 -W2 8.8.8.8 >/dev/null 2>&1; then echo "  LEAK: ICMP erreichbar"; fail=1; else echo "  ok: kein ICMP"; fi

echo "[airgap] DNS-Resolve (muss scheitern)"
if getent hosts example.com >/dev/null 2>&1; then echo "  LEAK: DNS aufloesbar"; fail=1; else echo "  ok: kein DNS"; fi

echo "[airgap] HTTP egress (muss scheitern)"
if curl -s --max-time 3 http://1.1.1.1 >/dev/null 2>&1; then echo "  LEAK: HTTP raus"; fail=1; else echo "  ok: kein HTTP"; fi

echo "[airgap] Default-Route (darf nicht existieren)"
if ip route | grep -q '^default'; then echo "  LEAK: Default-Route vorhanden"; fail=1; else echo "  ok: keine Default-Route"; fi

echo "[airgap] Lateral svc/Host (10.20.0.0/24 muss leer sein)"
if ping -c1 -W2 10.20.0.20 >/dev/null 2>&1; then echo "  LEAK: svc-Netz erreichbar"; fail=1; else echo "  ok: kein svc-Pfad"; fi

[ $fail -eq 0 ] && echo "[airgap] PASS: kein Egress" || echo "[airgap] FAIL: Egress-Pfad gefunden"
exit $fail
