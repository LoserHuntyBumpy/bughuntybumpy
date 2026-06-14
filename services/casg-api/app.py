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
"""BHB Layer-2 CASG - Context-Aware Submission Gateway (Controller).

Nimmt Submission von pie-web, prueft deterministisch (Plausibilitaet,
Selbstversuch, Ad-Hominem-Tonalitaet), persistiert Report, pusht Job in
redis-Queue fuer Layer-3-Broker. Keine generative KI. Geschaeftslogik der
Gate-Pruefung in gate.py (Service-Layer).
"""
import json
import os
import uuid

import psycopg2
import redis
from fastapi import FastAPI
from pydantic import BaseModel

import gate

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
QUEUE_REALTIME = "queue:realtime"

app = FastAPI(title="BHB casg-api")
rds = redis.from_url(REDIS_URL)


class Reframe(BaseModel):
    context: str = ""
    expectation: str = ""
    reality: str = ""
    selftest: str = ""
    solution: str = ""


class Repro(BaseModel):
    commit: str = ""
    steps: list = []


class Submission(BaseModel):
    project_id: str
    commit: str
    runtime: str = "docker"
    env_output: str = ""
    bug_class: str
    reframe: Reframe
    repro: Repro
    proof_of_context: dict = {}


def db():
    return psycopg2.connect(DATABASE_URL)


@app.get("/api/health")
def health():
    try:
        rds.ping()
        with db():
            pass
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@app.post("/api/submit")
def submit(s: Submission):
    checks = gate.validate(s.model_dump())
    if checks["reject"]:
        return {"status": "rejected", "reasons": checks["reasons"]}

    repro_class = gate.repro_class(s.bug_class)
    tone = checks["tone_tag"]
    repro_hash = gate.repro_hash(s.repro.model_dump())
    report_id = str(uuid.uuid4())

    with db() as conn, conn.cursor() as cur:
        # project_id muss existieren (FK). Bei fehlendem PIE-Run weich anlegen.
        cur.execute("INSERT INTO projects (id, bughunty_yml) VALUES (%s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (s.project_id, json.dumps({"stub": True})))
        cur.execute(
            "INSERT INTO reports (id, project_id, commit_hash, repro_class, "
            "tone_tag, repro_hash, repro_yml, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'queued')",
            (report_id, s.project_id, s.commit, repro_class, tone,
             repro_hash, json.dumps(s.repro.model_dump())))

    # Klasse C (manuell) geht NICHT in die Sandbox (Konzept 4.1).
    if repro_class == "C":
        _set_status(report_id, "community_queue")
        return {"status": "accepted", "report_id": report_id,
                "repro_class": "C", "note": "manuell, keine Sandbox",
                "tone_tag": tone}

    job = {"report_id": report_id, "project_id": s.project_id,
           "commit": s.commit, "repro": s.repro.model_dump()}
    rds.rpush(QUEUE_REALTIME, json.dumps(job))
    return {"status": "accepted", "report_id": report_id,
            "repro_class": repro_class, "tone_tag": tone, "queued": True}


def _set_status(report_id, status):
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE reports SET status=%s WHERE id=%s",
                    (status, report_id))
