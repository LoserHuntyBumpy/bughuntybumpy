#!/usr/bin/env bash
# host-firewall.sh - Sandbox-Airgap zweite Linie (Blueprint 5.4).
# Beim Deploy als root ausfuehren. iptables-Hard-Block fuer sandbox-subnet.
set -euo pipefail

NET=bughuntybumpy_sandbox
SANDBOX_SUBNET=$(docker network inspect "$NET" \
  -f '{{ (index .IPAM.Config 0).Subnet }}')

echo "sandbox subnet: $SANDBOX_SUBNET"
iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" ! -d "$SANDBOX_SUBNET" -j DROP
iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" -o eth0 -j DROP
echo "egress-block aktiv. Persistieren via iptables-save."
