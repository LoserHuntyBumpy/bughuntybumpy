#!/usr/bin/env bash
# host-firewall.sh - Sandbox-Airgap zweite Linie (Blueprint 5.4).
# Beim Deploy als root ausfuehren. iptables-Hard-Block fuer sandbox-subnet.
set -euo pipefail

NET=bughuntybumpy_sandbox
SANDBOX_SUBNET=$(docker network inspect "$NET" \
  -f '{{ (index .IPAM.Config 0).Subnet }}')

echo "sandbox subnet: $SANDBOX_SUBNET"
# Eine interface-unabhaengige Regel genuegt: alles aus dem Sandbox-Subnetz,
# das nicht ins Sandbox-Subnetz geht, wird verworfen (F-012: hartkodierte
# eth0-Zusatzregel entfernt, war redundant und interface-abhaengig).
iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" ! -d "$SANDBOX_SUBNET" -j DROP
echo "egress-block aktiv. Persistieren via iptables-save."
