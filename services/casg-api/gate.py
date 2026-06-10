#!/usr/bin/env python3
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
    if bug_class in TIER1 | TIER2 and not steps:
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
