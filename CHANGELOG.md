# Changelog

Alle wichtigen Aenderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt haelt sich an [Semantic Versioning](https://semver.org/lang/de/).

## [0.3.0] - 2026-06-13

VM-Infrastruktur als waehlbare Alternative zu Docker (UMSETZUNGSPLAN_VM-Alternative
v1.1). Docker bleibt Default, regressionsfrei.

### Hinzugefuegt
- Treiber-Interface `runner_driver.py` (Factory docker|vm), `vm_driver.py`
  (Backends hyperv/libvirt: Seed-ISO, Linked Clone, Timebox-Watchdog,
  garantiertes Destroy, Orphan-Sweep).
- Wahlmodell zwei Achsen: `STACK=compose|vm`, `RUNNER_BACKEND=docker|vm`.
  Gesperrte Kombi compose+vm bricht in `broker.check_combo()` hart ab.
- vm/-Gerust: Packer (Base + 5 Rollen), cloud-init (5), Terraform
  (hyperv|libvirt via profile), Ansible site.yml, Lifecycle-Skripte
  (010_build/020_provision/030_destroy/runner_spawn/orphan_sweep/040_airgap).
- BLUEPRINT_VM-Infrastruktur.md, README VM-Profil-Sektion.
- Unit-Tests test_docker_driver.py + test_vm_driver.py (spawn/timeout/
  destroy/orphan/gesperrte-Kombi).

### Geaendert
- broker.py entkoppelt: kein `import docker` auf Modul-Ebene mehr; Docker-Logik
  (run_job/ensure_networks/_parse_verdict) 1:1 nach docker_driver.py (lazy import).
  Dispatch nach RUNNER_BACKEND. Verhaltenserhaltend fuer Docker-Pfad.
- csve-broker/Dockerfile kopiert Treiber-Module zusaetzlich.
- .gitignore: vm/output, *.vhdx, *.qcow2, seed*.iso, terraform-State.

### Verifiziert
- RUNNER_BACKEND=docker bit-identisch (docker_driver-Tests gruen).
- pytest casg-api/pie-scanner/csve-broker: 29 passed.
- Image-Build/Provisionierung/Airgap (Akzeptanz 1-4) NICHT verifiziert —
  erfordern reale Hyper-V/Packer/Terraform-Toolchain (Plan Phase 0).

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
