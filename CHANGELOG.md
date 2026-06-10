# Changelog

Alle wichtigen Aenderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt haelt sich an [Semantic Versioning](https://semver.org/lang/de/).

## [0.2.0] - 2026-06-09

### In Arbeit / Behoben (Code + teilweise verifiziert)
- BUG-1: traefik Image v3.2 + Router-Prioritaeten (Diagnose nicht abgeschlossen, api/insecure fuer rawdata)
- BUG-2: sandbox/honeypot-net nie angelegt (SDK-idempotente Netz-Anlage in broker.py)
- BUG-3: Broker remove-race unter Docker 29 (detach+wait+finally remove)
- DEF-8: Job-Verlust bei Broker-Crash (BLMOVE + processing-Queue + reclaim). Idempotenz via UNIQUE(report_id) + ON CONFLICT.

### Geaendert
- DEF-4: runner.py shell=True -> shell=False mit ["sh","-c",cmd]-Liste. Shell-Features erhalten.
- DEF-6: scan.py _section manuelles Bracket-Counting -> json.loads mit Fehlerbehandlung.
- DEF-7: scan.py git-clone Timeout=120 Sekunden.
- DEF-9: BLUEPRINT Dokumentation: MVP-Reduktion TLS-Hinweis ergaenzt.

### Hinzugefuegt
- Unit-Tests fuer runner, gate, scanner, broker (pytest).
- CHANGELOG.md initial angelegt.

## [0.1.0] - 2026-06-05

### Hinzugefuegt
- Initialer MVP nach Blueprint v1.0 / Konzept4_Master-Fusion.md §9 Phase 1.
- Layer-1: pie-scanner (deterministische Repo-Analyse -> bughunty.yml)
- Layer-1: pie-web (FastAPI + Jinja, adaptives Formular)
- Layer-2: casg-api (Gate-Logik, Submission, Repro-Intake)
- Layer-3: csve-broker (Job-Queue-Consumer, Python-MVP statt Go)
- Layer-3: csve-runner (Closed-Shell, Exit-/Output-Assertion)
- Layer-5: relay-worker (GitHub-Badge-Mapping, Stub)
- Docker-Infrastruktur: traefik, postgres, redis, Netz-Trennung frontend/backend/sandbox
