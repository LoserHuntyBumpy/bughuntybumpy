#!/usr/bin/env python3
"""Persistiert bughunty.yml als JSONB in postgres.projects (upsert)."""
import json
import os
import sys

import yaml

try:
    import psycopg2
except ImportError:
    sys.stderr.write("psycopg2 fehlt\n")
    sys.exit(0)


def main(path):
    with open(path, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    pid = spec["project_id"]
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO projects (id, bughunty_yml) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET bughunty_yml = EXCLUDED.bughunty_yml",
            (pid, json.dumps(spec)),
        )
    conn.close()
    sys.stderr.write("persisted project %s\n" % pid)


if __name__ == "__main__":
    main(sys.argv[1])
