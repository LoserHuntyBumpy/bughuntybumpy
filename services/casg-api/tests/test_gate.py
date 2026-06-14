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
from gate import validate, repro_class, repro_hash


def test_selftest_missing():
    sub = {"reframe": {"selftest": "", "reality": "x", "expectation": "y"},
           "bug_class": "xss"}
    result = validate(sub)
    assert result["reject"] is True
    assert "selftest_empty" in result["reasons"]


def test_tone_emotional():
    sub = {"reframe": {"selftest": "x", "reality": "you are incompetent",
                       "expectation": "y"},
           "bug_class": "xss"}
    result = validate(sub)
    assert result["tone_tag"] == "emotional"


def test_tone_urgent():
    sub = {"reframe": {"selftest": "x", "reality": "fix this asap!!!",
                       "expectation": "y"},
           "bug_class": "xss"}
    result = validate(sub)
    assert result["tone_tag"] == "urgent"


def test_tone_neutral():
    sub = {"reframe": {"selftest": "x", "reality": "it crashes",
                       "expectation": "y"},
           "bug_class": "xss"}
    result = validate(sub)
    assert result["tone_tag"] == "neutral"


def test_repro_class_mapping():
    assert repro_class("xss") == "A"
    assert repro_class("race_condition") == "B"
    assert repro_class("feature_request") == "C"


def test_repro_hash_deterministic():
    r1 = {"steps": [{"run": "echo 1", "expect_output": "1"}]}
    h1 = repro_hash(r1)
    h2 = repro_hash(r1)
    assert h1 == h2
    assert isinstance(h1, str) and len(h1) == 64
