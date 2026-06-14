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
    _parse_verdict, DockerDriver, SANDBOX_NET, HONEYPOT_NET, TIMEBOX,
    STEP_TIMEOUT,
)


def _drv():
    return DockerDriver()


def test_parse_verdict():
    raw = b'some noise\n{"verdict": "V1"}\n'
    assert _parse_verdict(raw)["verdict"] == "V1"


def test_parse_verdict_empty():
    assert _parse_verdict(b"") is None


def test_timebox_exceeds_step_timeout():
    assert TIMEBOX > int(STEP_TIMEOUT)


def test_ensure_networks_creates_missing():
    drv = _drv()
    drv.dcli.networks.get.side_effect = mock_docker_errors.NotFound("x")
    drv.dcli.networks.create.reset_mock()
    drv.ensure_networks()
    assert drv.dcli.networks.create.call_count == 2
    calls = drv.dcli.networks.create.call_args_list
    assert calls[0][0][0] == SANDBOX_NET
    assert calls[1][0][0] == HONEYPOT_NET
    for c in calls:
        assert c.kwargs.get("internal") is True or c[1].get("internal") is True


def test_ensure_networks_idempotent():
    drv = _drv()
    drv.dcli.networks.get.side_effect = None
    drv.dcli.networks.create.reset_mock()
    drv.ensure_networks()
    drv.dcli.networks.create.assert_not_called()


@patch('docker_driver.shutil.rmtree')
@patch('docker_driver.tempfile.mkdtemp', return_value='/tmp/bhb-job-xyz')
def test_spawn_workdir_cleanup_on_error(mock_mkdtemp, mock_rmtree):
    drv = _drv()
    drv.dcli.containers.run.side_effect = Exception("docker fail")
    report = drv.spawn("r1", {"steps": []})
    assert report["verdict"] == "REJECTED"
    mock_rmtree.assert_called_once_with('/tmp/bhb-job-xyz', ignore_errors=True)
