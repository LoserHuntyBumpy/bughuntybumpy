#!/usr/bin/env python3
"""Runner-Treiber-Interface + Factory.

Entkoppelt csve-broker von der konkreten Sandbox-Technologie. Ein Treiber
erhaelt (report_id, repro) und liefert ein Verdikt-Dict zurueck. Der Broker
persistiert dieses Dict; der Treiber selbst kennt weder postgres noch redis.

Backends:
  docker  -> docker_driver.DockerDriver   (Ist, Default)
  vm      -> vm_driver.VMDriver           (neu, opt-in)

Lazy-Import der Backend-Module: ein VM-only-Host ohne python-docker darf
nicht beim broker-Import crashen (Interferenz-Pruefung Plan 1.5).
"""


class RunnerDriver:
    """Abstraktes Interface. spawn() liefert Verdikt-Dict (nie Exception)."""

    def setup(self):
        """Einmalige Vorbereitung (z. B. Netze anlegen). Default: no-op."""

    def spawn(self, report_id, repro):
        raise NotImplementedError

    def sweep_orphans(self):
        """Verwaiste Sandbox-Reste beim Broker-Start raeumen. Default: no-op."""


def get_driver(backend):
    """Treiber-Instanz fuer backend in {docker, vm}. Lazy-Import."""
    if backend == "docker":
        from docker_driver import DockerDriver
        return DockerDriver()
    if backend == "vm":
        from vm_driver import VMDriver
        return VMDriver()
    raise ValueError("unbekanntes RUNNER_BACKEND=%r (docker|vm)" % backend)
