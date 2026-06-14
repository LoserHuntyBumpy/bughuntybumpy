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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scan import _section


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
