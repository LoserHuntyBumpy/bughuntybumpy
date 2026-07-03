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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from throttle import check_quota


class FakeRedis:
    """Minimaler INCR/EXPIRE-Mock fuer Quota-Test (kein laufendes Redis)."""
    def __init__(self):
        self.store = {}
        self.expired = {}

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, ttl):
        self.expired[key] = ttl


class BrokenRedis:
    def incr(self, key):
        raise RuntimeError("redis down")

    def expire(self, key, ttl):
        raise RuntimeError("redis down")


def test_quota_allows_under_limit():
    rds = FakeRedis()
    for _ in range(5):
        assert check_quota(rds, "ip:1.2.3.4", 5) is True


def test_quota_blocks_over_limit():
    rds = FakeRedis()
    results = [check_quota(rds, "ip:1.2.3.4", 3) for _ in range(5)]
    assert results[:3] == [True, True, True]
    assert results[3:] == [False, False]


def test_quota_sets_expire_on_first_hit():
    rds = FakeRedis()
    check_quota(rds, "ip:9.9.9.9", 10)
    assert any(k.startswith("quota:ip:9.9.9.9") for k in rds.expired)


def test_quota_fail_open_on_redis_error():
    assert check_quota(BrokenRedis(), "ip:1.2.3.4", 1) is True
