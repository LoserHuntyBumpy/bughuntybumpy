#!/usr/bin/env python3
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
"""BHB Throttle-Service - Redis-Quota pro Schluessel (Service-Layer).

Plattformunabhaengig, keine HTTP-Imports. Einfache Sliding-Window-naehe
ueber Minuten-Bucket: INCR + EXPIRE. Zaehlt Requests pro Schluessel
(z. B. Client-IP) pro Kalenderminute, blockt ab limit_per_min.
"""
import time


def check_quota(rds, key, limit_per_min):
    """True wenn Request erlaubt, False bei Ueberschreitung.

    Minuten-Bucket-Key, erster Treffer setzt EXPIRE 60s. Redis-Fehler
    fail-open (kein Hard-Block bei Infra-Stoerung). Policy-Entscheid
    (Audit 2026-07-03 F-010): fail-open bewusst belassen; erste Linie
    gegen Flutung ist das traefik-Ratelimit (bhb-ratelimit, 30/min),
    das unabhaengig von Redis greift.
    """
    bucket = "quota:%s:%d" % (key, int(time.time()) // 60)
    try:
        count = rds.incr(bucket)
        if count == 1:
            rds.expire(bucket, 60)
        return count <= limit_per_min
    except Exception:  # noqa: BLE001
        return True
