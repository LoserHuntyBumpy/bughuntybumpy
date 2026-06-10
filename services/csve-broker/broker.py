#!/usr/bin/env python3
"""BHB Layer-3 csve-broker - Job-Consumer + Runner-Provisionierung.

MVP-Variante in Python (Blueprint sieht Go vor; MVP-Reduktion dokumentiert).
Liest Jobs aus redis:queue:realtime, schreibt repro.yml in ephemeren
Arbeitsordner, startet einen Closed-Shell csve-runner-Container (Netz:
sandbox + honeypot, read-only, cap-drop, kein Egress), liest Verdikt-JSON
von stdout, persistiert es und benachrichtigt relay-worker.

KEINE generative KI. Reine Orchestrierung.
"""
import json
import os
import shutil
import tempfile
import time

import docker
import psycopg2
import redis
import yaml

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
RUNNER_IMAGE = os.getenv("RUNNER_IMAGE", "bhb/csve-runner:latest")
STEP_TIMEOUT = os.getenv("STEP_TIMEOUT_SEC", "120")
TIMEBOX = int(os.getenv("REALTIME_TIMEBOX_SEC", "600"))
QUEUE = "queue:realtime"
PROCESSING = "queue:realtime:processing"
NOTIFY = "queue:verdicts"

SANDBOX_NET = "bughuntybumpy_sandbox"
HONEYPOT_NET = "bughuntybumpy_honeypot-net"

rds = redis.from_url(REDIS_URL)
dcli = docker.from_env()


def db():
    return psycopg2.connect(DATABASE_URL)


def ensure_networks():
    for net in (SANDBOX_NET, HONEYPOT_NET):
        try:
            dcli.networks.get(net)
        except docker.errors.NotFound:
            dcli.networks.create(net, driver="bridge", internal=True)


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


def run_job(job):
    report_id = job["report_id"]
    repro = job["repro"]
    workdir = tempfile.mkdtemp(prefix="bhb-job-")
    try:
        repro_path = os.path.join(workdir, "repro.yml")
        with open(repro_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(repro, fh, sort_keys=False)

        container = dcli.containers.run(
            RUNNER_IMAGE,
            command=["/repro/repro.yml"],
            volumes={workdir: {"bind": "/repro", "mode": "ro"}},
            network=SANDBOX_NET,
            environment={"STEP_TIMEOUT_SEC": STEP_TIMEOUT, "NO_EGRESS": "1"},
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            pids_limit=256,
            mem_limit="2g",
            nano_cpus=2_000_000_000,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=512m"},
            detach=True,
            stdout=True, stderr=True,
        )
        try:
            container.wait(timeout=TIMEBOX)
            logs = container.logs(stdout=True, stderr=False)
            report = _parse_verdict(logs) or {
                "verdict": "REJECTED", "verdict_class": "none",
                "error": "no_verdict_in_logs"}
        except Exception:  # noqa: BLE001
            report = {"verdict": "REJECTED", "verdict_class": "none",
                      "error": "wait_or_log_error"}
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass
    except Exception as e:  # noqa: BLE001
        report = {"verdict": "REJECTED", "verdict_class": "none",
                  "error": str(e)}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    persist_verdict(report_id, report)


def _parse_verdict(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    for line in reversed(raw.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


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
    ensure_networks()
    reclaim_processing()
    print("csve-broker up, consuming %s" % QUEUE, flush=True)
    while True:
        raw = rds.blmove(QUEUE, PROCESSING, timeout=5, src="LEFT", dest="RIGHT")
        if not raw:
            continue
        try:
            job = json.loads(raw)
            run_job(job)
        except Exception as e:  # noqa: BLE001
            print("job error: %s" % e, flush=True)
            time.sleep(1)
        finally:
            rds.lrem(PROCESSING, 0, raw)


if __name__ == "__main__":
    main()
