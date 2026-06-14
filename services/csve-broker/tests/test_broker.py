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
import json
from unittest.mock import MagicMock

for mod in ('psycopg2', 'redis'):
    sys.modules[mod] = MagicMock()

os.environ.setdefault("DATABASE_URL", "postgresql://x/x")
os.environ.setdefault("REDIS_URL", "redis://x/0")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker
from broker import (
    severity_for, reclaim_processing, persist_verdict, run_job, check_combo,
)


def test_severity_for():
    assert severity_for({"verdict": "V1"}) == "P1"
    assert severity_for({"verdict": "V2"}) == "P3"
    assert severity_for({"verdict": "REJECTED"}) == "P4"
    assert severity_for({}) == "P4"


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


def test_check_combo_locked_aborts():
    with pytest.raises(SystemExit):
        check_combo("compose", "vm")


def test_check_combo_valid_pass():
    # gueltige Kombis duerfen nicht abbrechen
    assert check_combo("compose", "docker") is None
    assert check_combo("vm", "vm") is None
    assert check_combo("vm", "docker") is None


def test_run_job_dispatches_to_driver_and_persists():
    driver = MagicMock()
    driver.spawn.return_value = {"verdict": "V1"}
    mock_conn = MagicMock()
    orig_db = broker.db
    broker.db = lambda: mock_conn
    try:
        run_job(driver, {"report_id": "r9", "repro": {"steps": []}})
        driver.spawn.assert_called_once_with("r9", {"steps": []})
        # NOTIFY-Push mit korrektem Verdikt
        pushed = broker.rds.rpush.call_args[0][1]
        assert json.loads(pushed)["verdict"] == "V1"
    finally:
        broker.db = orig_db
