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
