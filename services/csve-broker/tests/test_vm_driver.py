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

import sys
import os
import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vm_driver
from vm_driver import VMDriver


def _drv(tmp):
    return VMDriver(backend="libvirt", script_dir=str(tmp))


def test_bad_backend_raises():
    with pytest.raises(ValueError):
        VMDriver(backend="xen", script_dir="/x")


def test_backend_selects_script():
    hv = VMDriver(backend="hyperv", script_dir="/s")
    assert hv.spawn_script.endswith("runner_spawn.ps1")
    lv = VMDriver(backend="libvirt", script_dir="/s")
    assert lv.spawn_script.endswith("runner_spawn.sh")


@patch('vm_driver.subprocess.run')
def test_spawn_happy_path(mock_run, tmp_path):
    drv = _drv(tmp_path)

    def fake_run(cmd, **kw):
        out = cmd[cmd.index("--verdict-out") + 1]
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"verdict": "V1", "verdict_class": "auth"}, fh)
        return MagicMock(returncode=0)

    mock_run.side_effect = fake_run
    report = drv.spawn("r1", {"steps": [{"run": "x"}]})
    assert report["verdict"] == "V1"


@patch('vm_driver.subprocess.run')
def test_spawn_timeout(mock_run, tmp_path):
    drv = _drv(tmp_path)
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=1)
    report = drv.spawn("r1", {"steps": []})
    assert report["verdict"] == "REJECTED"
    assert report["error"] == "vm_timebox_exceeded"


@patch('vm_driver.subprocess.run')
def test_spawn_called_process_error(mock_run, tmp_path):
    drv = _drv(tmp_path)
    mock_run.side_effect = subprocess.CalledProcessError(returncode=3, cmd="x")
    report = drv.spawn("r1", {"steps": []})
    assert report["verdict"] == "REJECTED"
    assert "vm_spawn_failed" in report["error"]


@patch('vm_driver.subprocess.run')
def test_spawn_no_verdict_file(mock_run, tmp_path):
    drv = _drv(tmp_path)
    mock_run.return_value = MagicMock(returncode=0)  # schreibt verdict.json nicht
    report = drv.spawn("r1", {"steps": []})
    assert report["error"] == "no_verdict_from_vm"


@patch('vm_driver.subprocess.run')
def test_spawn_verdict_parse_error(mock_run, tmp_path):
    drv = _drv(tmp_path)

    def fake_run(cmd, **kw):
        out = cmd[cmd.index("--verdict-out") + 1]
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("not json{{")
        return MagicMock(returncode=0)

    mock_run.side_effect = fake_run
    report = drv.spawn("r1", {"steps": []})
    assert report["error"] == "verdict_parse_error"


@patch('vm_driver.subprocess.run')
def test_sweep_orphans_noop_without_script(mock_run, tmp_path):
    drv = _drv(tmp_path)  # script_dir leer -> kein orphan_sweep.sh
    drv.sweep_orphans()
    mock_run.assert_not_called()
