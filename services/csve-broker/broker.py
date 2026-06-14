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
"""BHB Layer-3 csve-broker - Job-Consumer + Runner-Provisionierung.

MVP-Variante in Python (Blueprint sieht Go vor; MVP-Reduktion dokumentiert).
Liest Jobs aus redis:queue:realtime, dispatcht die Sandbox-Ausfuehrung an
einen austauschbaren Runner-Treiber (docker | vm), persistiert das Verdikt
und benachrichtigt relay-worker.

Treiber-Entkopplung (Plan 1.5 / Phase 3): broker kennt KEINE konkrete
Sandbox-Technologie mehr. `import docker` liegt ausschliesslich im
docker_driver (lazy). Backend-Wahl via RUNNER_BACKEND (docker|vm), Stack-Wahl
via STACK (compose|vm). Gesperrte Kombi STACK=compose + RUNNER_BACKEND=vm
wird beim Start hart abgewiesen (Plan 3.5).

KEINE generative KI. Reine Orchestrierung.
"""
import json
import os
import sys
import time

import psycopg2
import redis

from runner_driver import get_driver

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
RUNNER_BACKEND = os.getenv("RUNNER_BACKEND", "docker")
STACK = os.getenv("STACK", "compose")
QUEUE = "queue:realtime"
PROCESSING = "queue:realtime:processing"
NOTIFY = "queue:verdicts"

rds = redis.from_url(REDIS_URL)


def db():
    return psycopg2.connect(DATABASE_URL)


def check_combo(stack, backend):
    """Gesperrte Kombi §3.5: containerisierter Broker kann Host-Hypervisor
    nicht treiben. Harter Abbruch statt stiller Fehlbedienung."""
    if stack == "compose" and backend == "vm":
        raise SystemExit(
            "gesperrte Kombination STACK=compose + RUNNER_BACKEND=vm: "
            "containerisierter Broker kann Host-Hypervisor nicht treiben. "
            "Stack=vm waehlen oder RUNNER_BACKEND=docker.")


def reclaim_processing():
    """Beim Restart: Jobs aus PROCESSING zurueck in QUEUE schieben."""
    while True:
        raw = rds.rpoplpush(PROCESSING, QUEUE)
        if not raw:
            break
        print("reclaimed job from processing", flush=True)


def severity_for(report):
    cls = report.get("verdict")
    if cls == "V1":
        return "P1"
    if cls == "V2":
        return "P3"
    return "P4"


def run_job(driver, job):
    report_id = job["report_id"]
    repro = job["repro"]
    report = driver.spawn(report_id, repro)
    persist_verdict(report_id, report)


def persist_verdict(report_id, report):
    verdict = report.get("verdict", "REJECTED")
    sev = severity_for(report)
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO verdicts (report_id, verdict, severity, detail) "
            "VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (report_id) DO NOTHING",
            (report_id, verdict, sev, json.dumps(report)))
        cur.execute("UPDATE reports SET status=%s WHERE id=%s",
                    ("verified" if verdict == "V1" else "closed", report_id))
    rds.rpush(NOTIFY, json.dumps(
        {"report_id": report_id, "verdict": verdict, "severity": sev}))
    print("verdict %s report=%s sev=%s" % (verdict, report_id, sev),
          flush=True)


def main():
    check_combo(STACK, RUNNER_BACKEND)
    driver = get_driver(RUNNER_BACKEND)
    driver.setup()
    driver.sweep_orphans()
    reclaim_processing()
    print("csve-broker up, backend=%s consuming %s" % (RUNNER_BACKEND, QUEUE),
          flush=True)
    while True:
        raw = rds.blmove(QUEUE, PROCESSING, timeout=5, src="LEFT", dest="RIGHT")
        if not raw:
            continue
        try:
            job = json.loads(raw)
            run_job(driver, job)
        except Exception as e:  # noqa: BLE001
            print("job error: %s" % e, flush=True)
            time.sleep(1)
        finally:
            rds.lrem(PROCESSING, 0, raw)


if __name__ == "__main__":
    main()
