#!/usr/bin/env python3
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
    steps = spec.get("steps", [])
    if not steps:
        verified = False
    for step in steps:
        r = run_step(step.get("run", "true"),
                     expect_exit=step.get("expect_exit"),
                     expect_substr=step.get("expect_output"))
        results.append(r)
        if not r["matched"]:
            verified = False
            break

    report = {
        "verdict": "V1" if verified else "REJECTED",
        "verdict_class": "deterministic" if verified else "none",
        "steps": results,
        "repro_hash": hashlib.sha256(
            open(repro_path, "rb").read()).hexdigest(),
        "step_count": len(steps),
    }
    sys.stdout.write(json.dumps(report) + "\n")
    sys.stdout.flush()
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
