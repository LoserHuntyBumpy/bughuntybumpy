#!/bin/sh
# Closed-Shell-Eintritt. Arg = Pfad zur repro.yml (read-only gemountet).
set -e
exec python3 /opt/runner.py "${1:-/repro/repro.yml}"
