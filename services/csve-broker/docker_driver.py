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
import io
import json
import os
import tarfile

import yaml

from runner_driver import RunnerDriver

RUNNER_IMAGE = os.getenv("RUNNER_IMAGE", "bhb/csve-runner:latest")
STEP_TIMEOUT = os.getenv("STEP_TIMEOUT_SEC", "120")
MAX_STEPS = os.getenv("MAX_STEPS", "50")
TIMEBOX = int(os.getenv("REALTIME_TIMEBOX_SEC", "600"))
SECCOMP_PROFILE = os.getenv("SECCOMP_PROFILE", "/etc/bhb/seccomp.json")

# Geteilte Sandbox-/Honeypot-Netze entfallen: jeder Job laeuft in einem
# eigenen ephemeren internen Netz (bhb-job-<report_id>), das nach Job-Ende
# wieder entfernt wird. Konsistenz mit Compose (kein dauerhaftes Runner-Netz).


def _seccomp_opt():
    """seccomp-Profil als inline-JSON. python-docker-SDK liest keinen
    Client-Pfad (anders als CLI) -> Datei-Inhalt selbst einlesen und als
    security_opt-Wert uebergeben. Fehlt die Datei -> graceful skip."""
    try:
        with open(SECCOMP_PROFILE, "r", encoding="utf-8") as fh:
            return "seccomp=" + fh.read()
    except OSError:
        return None


def _repro_tar(repro):
    """repro.yml als In-Memory-Tar fuer put_archive. Kein Host-Pfad:
    Broker-Container-Pfade sind fuer den Docker-Daemon (Host-Namespace,
    Socket-Mount) unsichtbar (D-001)."""
    data = yaml.safe_dump(repro, sort_keys=False).encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo("repro.yml")
        info.size = len(data)
        info.mode = 0o444  # lesbar fuer Runner-User (uid 10001)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


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
        # Kein geteiltes Sandbox-Netz mehr: jeder Job bekommt ein eigenes
        # ephemeres internes Netz (siehe spawn), damit parallele Runner sich
        # nicht erreichen koennen. Nichts vorzubereiten.
        pass

    def spawn(self, report_id, repro):
        # D-001: kein Bind-Mount aus dem Broker-Dateisystem - der Daemon
        # aufloest Bind-Pfade im HOST-Namespace. Stattdessen benanntes
        # Volume pro Job, befuellt via put_archive auf einem nicht
        # gestarteten Hilfscontainer (Runner-Image, kein Zusatz-Image).
        vol_name = "bhb-job-%s" % report_id
        net_name = "bhb-job-%s" % report_id
        vol = None
        net = None
        container = None
        try:
            vol = self.dcli.volumes.create(vol_name)
            helper = self.dcli.containers.create(
                RUNNER_IMAGE, entrypoint="true",
                volumes={vol_name: {"bind": "/repro", "mode": "rw"}})
            try:
                helper.put_archive("/repro", _repro_tar(repro))
            finally:
                try:
                    helper.remove(force=True)
                except Exception:  # noqa: BLE001
                    pass

            # Ephemeres, internes Job-Netz: pro Job isoliert, kein Egress,
            # keine Sicht auf parallele Runner.
            net = self.dcli.networks.create(
                net_name, driver="bridge", internal=True)

            sec = ["no-new-privileges:true"]
            seccomp = _seccomp_opt()
            if seccomp is not None:
                sec.append(seccomp)

            container = self.dcli.containers.run(
                RUNNER_IMAGE,
                command=["/repro/repro.yml"],
                volumes={vol_name: {"bind": "/repro", "mode": "ro"}},
                network=net_name,
                environment={"STEP_TIMEOUT_SEC": STEP_TIMEOUT, "NO_EGRESS": "1",
                             "MAX_STEPS": MAX_STEPS,
                             "REALTIME_TIMEBOX_SEC": str(TIMEBOX)},
                read_only=True,
                cap_drop=["ALL"],
                security_opt=sec,
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
                # wait-Timeout ist nur HTTP-Read-Timeout, kein Kill:
                # Container haerter toeten, sonst laeuft er weiter.
                try:
                    container.kill()
                except Exception:
                    pass
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
            if net is not None:
                try:
                    net.remove()
                except Exception:
                    pass
            if vol is not None:
                try:
                    vol.remove(force=True)
                except Exception:
                    pass
        return report
