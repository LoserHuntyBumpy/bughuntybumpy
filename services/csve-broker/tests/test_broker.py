import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch, call

for mod in ('docker', 'psycopg2', 'redis'):
    sys.modules[mod] = MagicMock()

mock_docker_mod = sys.modules['docker']
mock_docker_errors = MagicMock()
mock_docker_errors.NotFound = Exception
mock_docker_mod.errors = mock_docker_errors

os.environ.setdefault("DATABASE_URL", "postgresql://x/x")
os.environ.setdefault("REDIS_URL", "redis://x/0")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker
from broker import (
    _parse_verdict, severity_for, ensure_networks,
    reclaim_processing, persist_verdict, run_job,
    SANDBOX_NET, HONEYPOT_NET, TIMEBOX, STEP_TIMEOUT,
)


def test_parse_verdict():
    raw = b'some noise\n{"verdict": "V1"}\n'
    assert _parse_verdict(raw)["verdict"] == "V1"


def test_parse_verdict_empty():
    assert _parse_verdict(b"") is None


def test_severity_for():
    assert severity_for({"verdict": "V1"}) == "P1"
    assert severity_for({"verdict": "V2"}) == "P3"
    assert severity_for({"verdict": "REJECTED"}) == "P4"
    assert severity_for({}) == "P4"


def test_ensure_networks_creates_missing():
    broker.dcli.networks.get.side_effect = broker.docker.errors.NotFound("x")
    broker.dcli.networks.create.reset_mock()
    ensure_networks()
    assert broker.dcli.networks.create.call_count == 2
    calls = broker.dcli.networks.create.call_args_list
    assert calls[0][0][0] == SANDBOX_NET
    assert calls[1][0][0] == HONEYPOT_NET
    # internal=True Pruefung via kwargs
    for c in calls:
        assert c.kwargs.get("internal") is True or c[1].get("internal") is True


def test_ensure_networks_idempotent():
    broker.dcli.networks.get.side_effect = None
    broker.dcli.networks.create.reset_mock()
    ensure_networks()
    broker.dcli.networks.create.assert_not_called()


def test_reclaim_processing():
    broker.rds.rpoplpush.side_effect = [b'job1', b'job2', None]
    reclaim_processing()
    assert broker.rds.rpoplpush.call_count == 3
    broker.rds.rpoplpush.assert_any_call("queue:realtime:processing", "queue:realtime")


def test_persist_verdict_idempotent():
    mock_conn = MagicMock()
    orig_db = broker.db
    broker.db = lambda: mock_conn
    try:
        persist_verdict("r1", {"verdict": "V1"})
        cur = mock_conn.__enter__.return_value.cursor.return_value.__enter__.return_value
        sql = cur.execute.call_args_list[0][0][0]
        assert "ON CONFLICT" in sql
    finally:
        broker.db = orig_db


def test_timebox_exceeds_step_timeout():
    assert TIMEBOX > int(STEP_TIMEOUT)


@patch('broker.shutil.rmtree')
@patch('broker.tempfile.mkdtemp', return_value='/tmp/bhb-job-xyz')
def test_run_job_workdir_cleanup(mock_mkdtemp, mock_rmtree):
    broker.dcli.containers.run.side_effect = Exception("docker fail")
    run_job({"report_id": "r1", "repro": {"steps": []}})
    mock_rmtree.assert_called_once_with('/tmp/bhb-job-xyz', ignore_errors=True)
