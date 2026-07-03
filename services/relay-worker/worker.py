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
"""BHB Layer-5 relay-worker - Verdikt -> GitHub-Label-Mapping (Stub).

Consumed queue:verdicts. Mappt Verdikt-Klasse auf Maintainer-Label und
erzeugt das Output-Paket (Konzept 6.5). GitHub-App-Call ist Stub (MVP):
ohne gueltige App-ID wird nur geloggt. Zwei-Spur-Prinzip (6.4): native
Issues bleiben, BHB priorisiert per Label.
"""
import json
import os
from contextlib import closing

import psycopg2
import redis

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "000000")
NOTIFY = "queue:verdicts"
PROCESSING = "queue:verdicts:processing"
DEAD = "queue:verdicts:dead"

# V2/V3 reserviert (Phase-2 Tier-B): Runner emittiert real nur V1/REJECTED.
# Label-Eintraege bleiben vorhanden, Tier-B-Logik noch nicht aktiv.
LABEL = {"V1": "bhb-verified", "V2": "bhb-stochastic",
         "V3": "bhb-community", "REJECTED": "bhb-rejected"}

rds = redis.from_url(REDIS_URL)


def db():
    return psycopg2.connect(DATABASE_URL)


def report_meta(report_id):
    with closing(db()) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT project_id, commit_hash, tone_tag "
                    "FROM reports WHERE id=%s", (report_id,))
        return cur.fetchone()


def handle(msg):
    rid = msg["report_id"]
    verdict = msg["verdict"]
    label = LABEL.get(verdict, "bhb-rejected")
    meta = report_meta(rid) or ("?", "?", "neutral")
    project, commit, tone = meta

    pkg = (
        "## [%s] Report %s\n"
        "Status:  %s\nCommit:  %s\nSeverity: %s\nTone:    %s\nProject: %s\n"
        % (label, rid[:8], verdict, str(commit)[:10],
           msg.get("severity", "P4"), tone, project))

    if GITHUB_APP_ID == "000000":
        print("[stub] kein GitHub-App-Key. Label=%s\n%s" % (label, pkg),
              flush=True)
    else:
        # Phase 2: echte GitHub-App-Integration (Label + Badge-Kommentar).
        print("[github] would set label %s on %s" % (label, project),
              flush=True)


def reclaim_processing():
    """Beim Restart: Nachrichten aus PROCESSING zurueck in NOTIFY schieben."""
    while True:
        raw = rds.rpoplpush(PROCESSING, NOTIFY)
        if not raw:
            break
        print("reclaimed verdict from processing", flush=True)


def main():
    reclaim_processing()
    print("relay-worker up, consuming %s" % NOTIFY, flush=True)
    while True:
        raw = rds.blmove(NOTIFY, PROCESSING, timeout=5, src="LEFT",
                         dest="RIGHT")
        if not raw:
            continue
        try:
            handle(json.loads(raw))
        except Exception as e:  # noqa: BLE001
            # Reliable-Queue (F-007): fehlgeschlagene Nachricht nicht
            # verlieren, sondern in Dead-Letter schieben (analog Broker).
            print("relay error (dead-letter): %s" % e, flush=True)
            rds.rpush(DEAD, raw)
        finally:
            rds.lrem(PROCESSING, 0, raw)


if __name__ == "__main__":
    main()
