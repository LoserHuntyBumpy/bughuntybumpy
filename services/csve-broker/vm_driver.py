#!/usr/bin/env python3
"""VM-Backend fuer csve-broker. Ephemere Runner-VM statt docker run.

Gleiches Interface wie docker_driver.DockerDriver: spawn(report_id, repro)
-> Verdikt-Dict. Pro Job:
  1. Seed-ISO (NoCloud) aus repro.yml erzeugen -> KEIN Netz-Transfer in Sandbox.
  2. Linked-Clone der Golden-Runner-Disk, nur sandbox-switch, kein Uplink.
  3. VM starten, systemd-Unit fuehrt runner.py aus.
  4. Verdikt ueber Hypervisor-Kanal einsammeln (Hyper-V KVP / virtio-serial).
  5. Garantiertes Destroy (try/finally), auch bei Timeout/Crash.

Lifecycle delegiert an Skripte vm/scripts/runner_spawn.{ps1,sh} ueber das
gewaehlte VM_BACKEND. Verdikt-JSON-Schema (V1/V2/REJECTED) unveraendert.
"""
import json
import os
import shutil
import subprocess
import tempfile

import yaml

from runner_driver import RunnerDriver

TIMEBOX = int(os.getenv("REALTIME_TIMEBOX_SEC", "600"))
VM_BACKEND = os.getenv("VM_BACKEND", "hyperv")  # hyperv | libvirt
VM_SCRIPT_DIR = os.getenv(
    "VM_SCRIPT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "vm", "scripts"))

_REJECT = {"verdict": "REJECTED", "verdict_class": "none"}


def _reject(reason):
    r = dict(_REJECT)
    r["error"] = reason
    return r


class VMDriver(RunnerDriver):
    def __init__(self, backend=None, script_dir=None):
        self.backend = backend or VM_BACKEND
        self.script_dir = script_dir or VM_SCRIPT_DIR
        if self.backend == "hyperv":
            self.spawn_script = os.path.join(self.script_dir, "runner_spawn.ps1")
        elif self.backend == "libvirt":
            self.spawn_script = os.path.join(self.script_dir, "runner_spawn.sh")
        else:
            raise ValueError("unbekanntes VM_BACKEND=%r (hyperv|libvirt)"
                             % self.backend)

    def _cmd(self, job_id, seed_iso, verdict_out):
        """Lifecycle-Kommando: Clone+Start+Collect+Destroy in einem Skript."""
        if self.backend == "hyperv":
            return ["powershell", "-NoProfile", "-File", self.spawn_script,
                    "-JobId", job_id, "-SeedIso", seed_iso,
                    "-VerdictOut", verdict_out, "-TimeboxSec", str(TIMEBOX)]
        return [self.spawn_script, "--job-id", job_id, "--seed-iso", seed_iso,
                "--verdict-out", verdict_out, "--timebox", str(TIMEBOX)]

    def _build_seed_iso(self, workdir, report_id, repro):
        """repro.yml in NoCloud-Seed schreiben. ISO-Bau via genisoimage/
        oscdimg uebernimmt das Spawn-Skript host-seitig (kein Netz)."""
        repro_path = os.path.join(workdir, "repro.yml")
        with open(repro_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(repro, fh, sort_keys=False)
        meta_path = os.path.join(workdir, "meta-data")
        with open(meta_path, "w", encoding="utf-8") as fh:
            fh.write("instance-id: bhb-runner-%s\n" % report_id)
        return workdir  # Seed-Verzeichnis; Skript erzeugt seed.iso daraus

    def spawn(self, report_id, repro):
        workdir = tempfile.mkdtemp(prefix="bhb-vm-")
        verdict_out = os.path.join(workdir, "verdict.json")
        try:
            seed = self._build_seed_iso(workdir, report_id, repro)
            try:
                subprocess.run(
                    self._cmd(report_id, seed, verdict_out),
                    timeout=TIMEBOX + 60, check=True,
                    capture_output=True)
            except subprocess.TimeoutExpired:
                return _reject("vm_timebox_exceeded")
            except subprocess.CalledProcessError as e:
                return _reject("vm_spawn_failed:%s" % e.returncode)
            if not os.path.exists(verdict_out):
                return _reject("no_verdict_from_vm")
            with open(verdict_out, encoding="utf-8") as fh:
                try:
                    return json.load(fh)
                except json.JSONDecodeError:
                    return _reject("verdict_parse_error")
        except Exception as e:  # noqa: BLE001
            return _reject(str(e))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def sweep_orphans(self):
        """Verwaiste Runner-VMs nach Broker-Crash entfernen."""
        script = "orphan_sweep.ps1" if self.backend == "hyperv" \
            else "orphan_sweep.sh"
        path = os.path.join(self.script_dir, script)
        if not os.path.exists(path):
            return
        cmd = (["powershell", "-NoProfile", "-File", path]
               if self.backend == "hyperv" else [path])
        try:
            subprocess.run(cmd, timeout=120, capture_output=True)
        except Exception:  # noqa: BLE001
            pass
