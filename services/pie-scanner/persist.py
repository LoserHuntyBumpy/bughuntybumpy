#!/usr/bin/env python3
# BugHuntyBumpy - Crowdsourced Bug-Bounty-Reporting-Gateway mit deterministischer Verifikation
# Copyright (C) 2026  Nope-im-not-pro  <nope-im-not-pro@keemail.me>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""Persistiert bughunty.yml als JSONB in postgres.projects (upsert)."""
import json
import os
import sys

import yaml

try:
    import psycopg2
except ImportError:
    # Exit != 0 (F-013): entrypoint.sh erkennt Skip nur am Exit-Code.
    sys.stderr.write("psycopg2 fehlt\n")
    sys.exit(1)


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
