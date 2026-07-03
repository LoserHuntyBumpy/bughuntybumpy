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
"""BHB Gate-Service - deterministische Pruef-Logik (Service-Layer).

Plattformunabhaengig, keine HTTP-Imports. Konzept 4.2-4.5:
- Selbstversuch-Pflicht (Missing-Context-Check).
- Reframe-Vollstaendigkeit.
- Ad-Hominem-Erkennung (Personenbezug + Negativattribut), Security-Sprache
  bleibt erlaubt -> setzt nur Tonalitaets-Tag, kein Ausschluss (4.3).
- Reproduzierbarkeits-Klasse aus Bug-Klasse.
- Dedup-Hash ueber Repro-Schritte.
"""
import hashlib
import re

TIER1 = {"xss", "sqli", "rce", "lfi", "crash", "dos_resource"}
TIER2 = {"race_condition", "logic_state_bug"}
TIER3 = {"feature_request", "ui_ux", "performance"}

# Security-Positivliste: technischer Kontext -> kein Flag.
SECURITY_TERMS = {"exploit", "shellcode", "privilege escalation", "segfault",
                  "injection", "kill process", "reverse shell", "payload"}
# Negativattribute mit Personenbezug -> Tonalitaets-Flag.
PERSON_REF = re.compile(r"\b(you|your|maintainer|dev|author|they|he|she)\b",
                        re.I)
NEG_ATTR = re.compile(r"\b(incompetent|stupid|idiot|lazy|garbage|trash|"
                      r"useless|shit|crap|moron|clueless|joke)\b", re.I)
URGENT = re.compile(r"\b(urgent|asap|immediately|now|critical|emergency|"
                    r"!!!)\b", re.I)


def validate(sub):
    reasons = []
    rf = sub.get("reframe", {})
    if not rf.get("selftest", "").strip():
        reasons.append("selftest_empty")          # Konzept 4.5 Missing-Context
    if not rf.get("reality", "").strip():
        reasons.append("reality_empty")
    if not rf.get("expectation", "").strip():
        reasons.append("expectation_empty")
    if not sub.get("commit", "").strip():
        reasons.append("commit_missing")

    steps = sub.get("repro", {}).get("steps", [])
    bug_class = sub.get("bug_class", "")
    if bug_class not in TIER1 | TIER2 | TIER3:
        reasons.append("unknown_bug_class")     # leerer/unbekannter Wert -> reject
    elif bug_class in TIER1 | TIER2 and not steps:
        reasons.append("repro_steps_required")

    tone = _tone(rf)
    return {"reject": bool(reasons), "reasons": reasons, "tone_tag": tone}


def _tone(reframe):
    blob = " ".join(str(v) for v in reframe.values())
    low = blob.lower()
    # Personenbezug + Negativattribut = emotional (Konzept 4.3 B).
    if PERSON_REF.search(blob) and NEG_ATTR.search(blob):
        return "emotional"
    if URGENT.search(blob):
        return "urgent"
    return "neutral"


def repro_class(bug_class):
    if bug_class in TIER3:
        return "C"
    if bug_class in TIER2:
        return "B"
    return "A"


def repro_hash(repro):
    norm = "|".join(
        "%s>%s" % (s.get("run", "").strip(), s.get("expect_output", ""))
        for s in repro.get("steps", []))
    return hashlib.sha256(norm.encode()).hexdigest()
