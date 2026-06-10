#!/bin/sh
# Oneshot: scannt Quelle, schreibt /spec/bughunty.yml (geteiltes Volume).
# Optional: persistiert Spec in postgres.projects.
set -e
SRC="${1:-/repos}"
python /opt/scan.py "$SRC" --out /spec/bughunty.yml
if [ -n "$DATABASE_URL" ]; then
  python /opt/persist.py /spec/bughunty.yml || \
    echo "persist skipped (db nicht erreichbar)"
fi
