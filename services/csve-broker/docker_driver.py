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
"""Docker-Backend fuer csve-broker. Ist-Logik 1:1 aus broker.py extrahiert.

Verhaltenserhaltend: identische Container-Optionen, identische Netz-Anlage,
identisches Verdikt-Parsing wie vor der Entkopplung. `import docker` erfolgt
ausschliesslich hier und lazy (erst bei Instanziierung), damit VM-only-Hosts
ohne python-docker den Broker-Import nicht brechen (Plan 1.5).
"""
import json
import os
import shutil
import tempfile

import yaml

from runner_driver import RunnerDriver

RUNNER_IMAGE = os.getenv("RUNNER_IMAGE", "bhb/csve-runner:latest")
STEP_TIMEOUT = os.getenv("STEP_TIMEOUT_SEC", "120")
TIMEBOX = int(os.getenv("REALTIME_TIMEBOX_SEC", "600"))

SANDBOX_NET = "bughuntybumpy_sandbox"
HONEYPOT_NET = "bughuntybumpy_honeypot-net"


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


class DockerDriver(RunnerDriver):
    def __init__(self):
        import docker  # lazy, nur im Docker-Backend
        self.docker = docker
        self.dcli = docker.from_env()

    def setup(self):
        self.ensure_networks()

    def ensure_networks(self):
        for net in (SANDBOX_NET, HONEYPOT_NET):
            try:
                self.dcli.networks.get(net)
            except self.docker.errors.NotFound:
                self.dcli.networks.create(net, driver="bridge", internal=True)

    def spawn(self, report_id, repro):
        workdir = tempfile.mkdtemp(prefix="bhb-job-")
        try:
            repro_path = os.path.join(workdir, "repro.yml")
            with open(repro_path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(repro, fh, sort_keys=False)

            container = self.dcli.containers.run(
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
        return report
