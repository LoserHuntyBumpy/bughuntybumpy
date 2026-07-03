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

import pytest

import sys
import os
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scan import _section, resolve_source


def test_section_json_nested():
    txt = '{"dependencies": {"a": {"b": 1}, "lodash": "4.0"}}'
    deps = _section(txt, "dependencies")
    assert '"lodash"' in deps


def test_section_malformed_json():
    assert _section("not json", "dependencies") == ""
    assert _section("", "dependencies") == ""


def test_section_missing_key():
    txt = '{"name": "foo"}'
    assert _section(txt, "dependencies") == ""


# ---------------------------------------------------------------- F5: RCE
@pytest.mark.parametrize("evil", [
    "ext::sh -c id",
    "ext::sh -c 'touch /tmp/pwned'",
    "file:///etc/passwd",
    "git://evil.example/repo",
    "ssh://git@evil.example/repo.git",
    "https://evil.example/repo.git",
    "-oProxyCommand=id",
])
def test_resolve_source_rejects_dangerous(evil):
    with mock.patch("scan.subprocess.run") as srun:
        with pytest.raises((ValueError, SystemExit)):
            resolve_source(evil)
        srun.assert_not_called()


def test_resolve_source_org_repo_clones_hardened():
    with mock.patch("scan.subprocess.run") as srun, \
            mock.patch("scan.tempfile.mkdtemp", return_value="/tmp/bhb-x"), \
            mock.patch("scan._git_head", return_value="deadbeef"):
        srun.return_value = mock.Mock(stdout="", stderr="")
        root, commit, pid = resolve_source("org/repo")
    assert pid == "org/repo"
    clone_argv = srun.call_args[0][0]
    assert clone_argv[0] == "git"
    assert "protocol.ext.allow=never" in clone_argv
    assert "clone" in clone_argv
    assert "https://github.com/org/repo.git" in clone_argv


def test_resolve_source_https_github_ok():
    with mock.patch("scan.subprocess.run") as srun, \
            mock.patch("scan.tempfile.mkdtemp", return_value="/tmp/bhb-y"), \
            mock.patch("scan._git_head", return_value="cafe"):
        srun.return_value = mock.Mock(stdout="", stderr="")
        resolve_source("https://github.com/org/repo")
    clone_argv = srun.call_args[0][0]
    assert "protocol.ext.allow=never" in clone_argv
    assert "https://github.com/org/repo.git" in clone_argv
