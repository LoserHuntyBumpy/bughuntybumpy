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
from unittest.mock import MagicMock, patch

# docker-Paket mocken (Lazy-Import im DockerDriver.__init__)
sys.modules['docker'] = MagicMock()
mock_docker_mod = sys.modules['docker']
mock_docker_errors = MagicMock()
mock_docker_errors.NotFound = Exception
mock_docker_mod.errors = mock_docker_errors

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import docker_driver
from docker_driver import (
    _parse_verdict, _seccomp_opt, DockerDriver, TIMEBOX, STEP_TIMEOUT,
)


def _drv():
    # frischer Client-Mock pro Test, sonst akkumulieren Call-Counts
    # ueber den geteilten sys.modules['docker']-Mock.
    mock_docker_mod.from_env.return_value = MagicMock()
    return DockerDriver()


def test_parse_verdict():
    raw = b'some noise\n{"verdict": "V1"}\n'
    assert _parse_verdict(raw)["verdict"] == "V1"


def test_parse_verdict_empty():
    assert _parse_verdict(b"") is None


def test_timebox_exceeds_step_timeout():
    assert TIMEBOX > int(STEP_TIMEOUT)


def test_spawn_volume_cleanup_on_error():
    # D-001: Job-Volume ersetzt Workdir; Cleanup auch im Fehlerfall.
    drv = _drv()
    vol = MagicMock()
    drv.dcli.volumes.create.return_value = vol
    drv.dcli.networks.create.side_effect = None
    drv.dcli.containers.run.side_effect = Exception("docker fail")
    report = drv.spawn("r1", {"steps": []})
    assert report["verdict"] == "REJECTED"
    vol.remove.assert_called_once_with(force=True)


def test_seccomp_opt_reads_profile_inline():
    # F2: Profil-Datei-Inhalt wird als inline-JSON-Wert geliefert.
    import unittest.mock as um
    data = '{"defaultAction":"SCMP_ACT_ERRNO"}'
    with um.patch('builtins.open', um.mock_open(read_data=data)):
        opt = _seccomp_opt()
    assert opt == "seccomp=" + data


def test_seccomp_opt_missing_file_skips():
    # F2: fehlende Datei -> None (graceful skip, kein Crash).
    import unittest.mock as um
    with um.patch('builtins.open', side_effect=OSError("no file")):
        assert _seccomp_opt() is None


@patch('docker_driver._seccomp_opt', return_value="seccomp={}")
def test_spawn_attaches_ephemeral_net_and_seccomp(mock_sec):
    # F2 + F8: pro Job ephemeres internes Netz, security_opt erweitert.
    drv = _drv()
    drv.dcli.networks.create.side_effect = None
    net = MagicMock()
    drv.dcli.networks.create.return_value = net
    container = MagicMock()
    drv.dcli.containers.run.side_effect = None
    drv.dcli.containers.run.return_value = container
    container.logs.return_value = b'{"verdict": "V1"}\n'

    report = drv.spawn("rABC", {"steps": []})

    # internes Job-Netz pro report_id angelegt ...
    drv.dcli.networks.create.assert_called_once()
    cargs = drv.dcli.networks.create.call_args
    assert cargs[0][0] == "bhb-job-rABC"
    assert cargs.kwargs.get("internal") is True
    # ... Container an genau dieses Netz gehaengt ...
    rkw = drv.dcli.containers.run.call_args.kwargs
    assert rkw["network"] == "bhb-job-rABC"
    # ... security_opt enthaelt no-new-privileges + seccomp ...
    assert "no-new-privileges:true" in rkw["security_opt"]
    assert "seccomp={}" in rkw["security_opt"]
    # ... und Job-Netz nach Job-Ende entfernt.
    net.remove.assert_called_once()
    assert report["verdict"] == "V1"


def test_spawn_transfers_repro_via_job_volume():
    # D-001: repro.yml erreicht den Runner ueber benanntes Job-Volume
    # (put_archive auf Hilfscontainer), kein Broker-Pfad als Bind-Mount.
    drv = _drv()
    vol = MagicMock()
    drv.dcli.volumes.create.return_value = vol
    drv.dcli.networks.create.return_value = MagicMock()
    helper = MagicMock()
    drv.dcli.containers.create.return_value = helper
    container = MagicMock()
    drv.dcli.containers.run.side_effect = None
    drv.dcli.containers.run.return_value = container
    container.logs.return_value = b'{"verdict": "V1"}\n'

    report = drv.spawn("rVOL", {"steps": [{"run": "echo hi"}]})

    # Volume pro Job angelegt, Hilfscontainer befuellt + entfernt ...
    drv.dcli.volumes.create.assert_called_once_with("bhb-job-rVOL")
    helper.put_archive.assert_called_once()
    assert helper.put_archive.call_args[0][0] == "/repro"
    helper.remove.assert_called_once_with(force=True)
    # ... Runner mountet Volume-Namen read-only ...
    rkw = drv.dcli.containers.run.call_args.kwargs
    assert rkw["volumes"] == {"bhb-job-rVOL": {"bind": "/repro",
                                               "mode": "ro"}}
    # ... Volume nach Job-Ende entfernt.
    vol.remove.assert_called_once_with(force=True)
    assert report["verdict"] == "V1"


def test_repro_tar_contains_repro_yml():
    # D-001: Tar-Payload enthaelt repro.yml mit YAML-Inhalt.
    import io
    import tarfile
    import yaml
    payload = docker_driver._repro_tar({"steps": [{"run": "echo hi"}]})
    with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
        member = tar.getmember("repro.yml")
        data = tar.extractfile(member).read()
    assert member.mode == 0o444
    assert yaml.safe_load(data) == {"steps": [{"run": "echo hi"}]}


def test_spawn_passes_step_caps_env():
    # F-006 (Audit 2026-07-03): MAX_STEPS + REALTIME_TIMEBOX_SEC erreichen
    # den Runner-Container, Operator-Konfig bleibt nicht wirkungslos.
    drv = _drv()
    drv.dcli.networks.create.side_effect = None
    drv.dcli.networks.create.return_value = MagicMock()
    container = MagicMock()
    drv.dcli.containers.run.side_effect = None
    drv.dcli.containers.run.return_value = container
    container.logs.return_value = b'{"verdict": "V1"}\n'

    drv.spawn("rENV", {"steps": []})

    env = drv.dcli.containers.run.call_args.kwargs["environment"]
    assert env["MAX_STEPS"] == docker_driver.MAX_STEPS
    assert env["REALTIME_TIMEBOX_SEC"] == str(TIMEBOX)
    assert env["STEP_TIMEOUT_SEC"] == STEP_TIMEOUT
    assert env["NO_EGRESS"] == "1"


def test_spawn_kills_container_on_wait_timeout():
    # F4: wait-Timeout -> harter kill VOR remove, Verdikt REJECTED.
    drv = _drv()
    drv.dcli.networks.create.side_effect = None
    drv.dcli.networks.create.return_value = MagicMock()
    container = MagicMock()
    drv.dcli.containers.run.side_effect = None
    drv.dcli.containers.run.return_value = container
    container.wait.side_effect = Exception("read timeout")

    report = drv.spawn("rTO", {"steps": []})

    container.kill.assert_called_once()
    container.remove.assert_called_once_with(force=True)
    assert report["verdict"] == "REJECTED"
    assert report["error"] == "wait_or_log_error"
