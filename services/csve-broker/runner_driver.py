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
