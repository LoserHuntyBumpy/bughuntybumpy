import json
import os
import sys
import tempfile

if sys.platform == "win32":
    import pytest
    pytest.skip("runner tests require Linux shell", allow_module_level=True)

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from runner import main, run_step, STEP_TIMEOUT


def cap_main(repro_path):
    import io
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        rc = main(repro_path)
    finally:
        out = sys.stdout.getvalue()
        sys.stdout = old
    return rc, out


def test_v1_pass():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.safe_dump({"commit": "abc", "steps": [
            {"run": "echo hello", "expect_exit": 0, "expect_output": "hello"}
        ]}, f)
        path = f.name
    rc, out = cap_main(path)
    os.unlink(path)
    data = json.loads(out.strip().splitlines()[-1])
    assert rc == 0
    assert data["verdict"] == "V1"
    assert data["verdict_class"] == "deterministic"


def test_rejected_fail():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.safe_dump({"commit": "abc", "steps": [
            {"run": "echo 3 rows", "expect_output": "1247 rows"}
        ]}, f)
        path = f.name
    rc, out = cap_main(path)
    os.unlink(path)
    data = json.loads(out.strip().splitlines()[-1])
    assert rc == 1
    assert data["verdict"] == "REJECTED"


def test_timeout():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.safe_dump({"commit": "abc", "steps": [
            {"run": "sleep %d" % (STEP_TIMEOUT + 2), "expect_exit": 0}
        ]}, f)
        path = f.name
    rc, out = cap_main(path)
    os.unlink(path)
    data = json.loads(out.strip().splitlines()[-1])
    assert data["verdict"] == "REJECTED"
    assert any(step.get("timed_out") for step in data["steps"])


def test_step_parse_deterministic():
    # Shell-Metazeichen duerfen bei shell=False keinen Exit-Code-Trick erzeugen
    r = run_step("false; true", expect_exit=0)
    assert r["matched"] is False


def test_shell_features_preserved():
    # Pipe mit sh -c muss funktionieren
    r = run_step("echo hello | grep hello", expect_substr="hello")
    assert r["matched"] is True
