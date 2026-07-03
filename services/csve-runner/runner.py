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
"""CSVE Closed-Shell Runner - deterministisch, KEINE KI.

Input: repro.yml (commit-pinned, Reporter-Playbook).
Output: Verdikt-JSON (V1/REJECTED) -> stdout. Erster Mismatch beendet
(Determinismus). Jeder Schritt: Exit-Code- und/oder Output-Assertion.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

import yaml

STEP_TIMEOUT = int(os.getenv("STEP_TIMEOUT_SEC", "120"))
MAX_STEPS = int(os.getenv("MAX_STEPS", "50"))
REALTIME_TIMEBOX_SEC = int(os.getenv("REALTIME_TIMEBOX_SEC", "600"))


def run_step(cmd, expect_exit=None, expect_substr=None):
    t0 = time.time()
    argv = cmd if isinstance(cmd, list) else ["sh", "-c", cmd]
    try:
        proc = subprocess.run(argv, shell=False, capture_output=True,
                              text=True, timeout=STEP_TIMEOUT)
        rc, out = proc.returncode, (proc.stdout + proc.stderr)[:50000]
        timed_out = False
    except subprocess.TimeoutExpired as e:
        rc, out, timed_out = 124, (e.output or "")[:50000], True

    ok = True
    if expect_exit is not None and rc != expect_exit:
        ok = False
    if expect_substr is not None and expect_substr not in out:
        ok = False
    return {
        "cmd": cmd, "exit": rc, "timed_out": timed_out,
        "duration_ms": int((time.time() - t0) * 1000),
        "output_hash": hashlib.sha256(out.encode()).hexdigest(),
        "matched": ok, "output_tail": out[-2000:],
    }


def main(repro_path):
    with open(repro_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    results, verified = [], True
    error = None
    steps = spec.get("steps", [])
    if not steps:
        verified = False

    if len(steps) > MAX_STEPS:
        verified = False
        error = "max_steps"
        steps = []

    t_start = time.time()
    for step in steps:
        if time.time() - t_start > REALTIME_TIMEBOX_SEC:
            verified = False
            error = "timebox_exceeded"
            break
        r = run_step(step.get("run", "true"),
                     expect_exit=step.get("expect_exit"),
                     expect_substr=step.get("expect_output"))
        results.append(r)
        if not r["matched"]:
            verified = False
            break
        if time.time() - t_start > REALTIME_TIMEBOX_SEC:
            verified = False
            error = "timebox_exceeded"
            break

    with open(repro_path, "rb") as fh:
        repro_hash = hashlib.sha256(fh.read()).hexdigest()

    report = {
        "verdict": "V1" if verified else "REJECTED",
        "verdict_class": "deterministic" if verified else "none",
        "steps": results,
        "repro_hash": repro_hash,
        "step_count": len(spec.get("steps", [])),
    }
    if error is not None:
        report["error"] = error
    sys.stdout.write(json.dumps(report) + "\n")
    sys.stdout.flush()
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
