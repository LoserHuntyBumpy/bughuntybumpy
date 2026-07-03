# Changelog

Alle wichtigen Aenderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt haelt sich an [Semantic Versioning](https://semver.org/lang/de/).

## [0.6.1] - 2026-07-03

Laufzeit-Defekte D-001/D-002 aus der 0.6.0-Verifikation.

### Geaendert
- docker_driver: repro.yml erreicht den Runner ueber ein benanntes
  Docker-Volume pro Job (`bhb-job-<id>`), befuellt via `put_archive` auf
  einem nicht gestarteten Hilfscontainer (Runner-Image). Vorher Bind-Mount
  eines Broker-Container-Pfads, den der Daemon im Host-Namespace aufloest
  -> leeres `/repro`, jeder reale Job REJECTED (D-001, hoch). Volume wird
  im `finally` entfernt; Netz-/Container-Cleanup unveraendert.
- compose: traefik `v3.2` -> `v3.6`. v3.2-v3.5 koennen Docker Engine 29
  (API 1.54) nicht lesen (400 auf `/info`, leere Fehlermeldung,
  BUG-1-Muster) -> Docker-Provider tot, Ingress 404 (D-002, mittel).
  Zusaetzlich `--providers.docker.network=bughuntybumpy_frontend`:
  Backends haengen in frontend+backend, ohne Pinning waehlt der Provider
  die fuer traefik unerreichbare backend-IP (504).

### Behoben
- D-001 Broker-Workdir-Mount erreicht Docker-Host nicht (jeder Job
  REJECTED `no_verdict_in_logs`).
- D-002 traefik-Docker-Provider inkompatibel mit Engine 29, Ingress-
  Routing tot (404/504 auf :6080).

### Verifiziert
- pytest: 51 passed, 1 skipped (Runner-Modul-Skip win32); neue Tests
  Volume-Transfer + Volume-Cleanup, Netz-/seccomp-/Env-/Kill-Assertions
  semantisch erhalten.
- Spawn im Container: `expect_exit:0` -> V1, `expect_exit:1` -> REJECTED;
  keine `bhb-job-*`-Volumes/-Netze nach Job-Ende.
- traefik v3.6: keine Provider-Fehler im Log; :6080/api/health 200,
  :6080/ 200 (Formular, Beispiel-Spec), Dashboard ohne Auth 401
  (loopback-only, Ratelimit/Bodylimit-Middlewares unveraendert aktiv).
- End-to-End: README-Smoke-Submit via :6080/api/submit -> Broker V1,
  verdicts-Tabelle 1 Eintrag, relay-worker loggt `bhb-verified`.
- `docker compose config -q` Exit 0; `py_compile` docker_driver OK.

## [0.6.0] - 2026-07-03

Audit-Fix-Batch aus AUDIT_2026-07-03 (F-001..F-013).

### Hinzugefuegt
- `deploy/01_bootstrap.sh`: generiert bei fehlendem/leerem
  `TRAEFIK_DASHBOARD_AUTH` einen apr1-htpasswd-Hash (openssl), Passwort
  einmalige Log-Anzeige (F-003).
- `.env.example`: `DOCKER_GID` (Socket-Gruppen-GID fuer non-root Broker, F-002).
- `.gitignore`: `!vm/scripts/*.ps1` (Laufzeit-Skripte VM-Profil, F-005),
  `*_token.json` (F-009).
- test_docker_driver: `test_spawn_passes_step_caps_env` (F-006).

### Geaendert
- casg-api Dockerfile kopiert `throttle.py` ins Image; Container startete
  zuvor nicht (`ModuleNotFoundError`, Regression aus 0.5.0) (F-001, kritisch).
- csve-broker laeuft non-root (User `broker`, GID via Build-Arg `DOCKER_GID`)
  mit `no-new-privileges:true`; Socket-Proxy bleibt Phase-2 (F-002).
- traefik-Dashboard: hartkodierter Default-htpasswd-Hash entfernt; leeres
  `TRAEFIK_DASHBOARD_AUTH` verweigert Start (`:?`-Interpolation) (F-003).
- `.gitignore`: `!INFRA.md` entfernt, INFRA.md aus Git-Index genommen -
  bleibt lokal, konsistent zur Eigen-Deklaration (F-004).
- docker_driver reicht `MAX_STEPS` + `REALTIME_TIMEBOX_SEC` an den
  Runner-Container durch; compose setzt `MAX_STEPS` am Broker (F-006).
- relay-worker: Reliable-Queue analog Broker (BLMOVE nach
  `queue:verdicts:processing`, LREM nach Erfolg, Dead-Letter
  `queue:verdicts:dead`, Reclaim beim Start) (F-007).
- host-firewall.sh: redundante interface-hartkodierte eth0-Regel entfernt;
  interface-unabhaengige Subnetz-Regel deckt Egress (F-012).
- persist.py: Exit 1 statt 0 bei fehlendem psycopg2, entrypoint.sh erkennt
  Skip (F-013).
- compose: totes `honeypot-net` samt Runner-Referenz entfernt (F-011).
- throttle.py: fail-open als Policy-Entscheid dokumentiert, traefik-Ratelimit
  als erste Linie (F-010, Verhalten unveraendert).

### Behoben
- F-001 casg-api-Image ohne throttle.py (kritisch), F-002 Broker root +
  ungehaertet (hoch), F-003 Default-Dashboard-Credential, F-004/F-005
  .gitignore-Inkonsistenzen, F-006 wirkungslose Runner-Konfig, F-007
  Verdikt-Verlust im Relay, F-008/F-009 veraltete Doku, F-011 tote
  Netz-Konfiguration, F-012 irrefuehrende iptables-Regel, F-013 stiller
  Persist-Skip.

### Verifiziert
- pytest: 49 passed, 1 skipped (Runner-Modul-Skip win32).
- `docker compose config -q` OK; leeres `TRAEFIK_DASHBOARD_AUTH` -> Abbruch.
- `py_compile` geaenderter Module OK; `bash -n` geaenderter Skripte OK.
- casg-api-Image gebaut, Container `healthy`, `import throttle` im Image OK.
  HTTP-Check via traefik blockiert durch vorbestehenden Docker-Provider-Fehler
  des Hosts (BUG-1-Muster), nicht durch F-001.
- Broker-Image non-root (uid 999, gid docker), `no-new-privileges` per
  inspect belegt, Docker-Socket-Ping als non-root OK, Runner-Spawn identisches
  Verhalten root vs. non-root.
- git check-ignore: INFRA.md ignoriert, `vm/scripts/runner_spawn.ps1` nicht
  ignoriert, `git_push.ps1` + `*_token.json` ignoriert.
- persist.py ohne psycopg2 -> Exit 1.

## [0.5.0] - 2026-06-26

Security-/Robustheits-Batch aus FixPlan_2026-06-25 (Audit 2026-06-25). 3 parallele
Coder-Agents, disjunkte Datei-Ownership, Reviewer-Sign-off durch Orchestrator.

### Hinzugefuegt
- `services/casg-api/throttle.py` (Service-Schicht): Redis-Minuten-Bucket-Quota
  `check_quota()`, fail-open. casg-api `/api/submit` blockt >30 Req/min/IP -> HTTP 429 (F3).
- Runner-ENV `MAX_STEPS` (Default 50) + Wall-Clock-Guard `REALTIME_TIMEBOX_SEC`:
  >MAX_STEPS -> REJECTED `error=max_steps`, Zeitueberschreitung -> `error=timebox_exceeded` (F4).
- traefik-Middlewares `bhb-ratelimit` (average=30/burst=15) + `bhb-bodylimit`
  (maxRequestBodyBytes=1MB) auf pie/casgapi-Router (F3).
- Compose-healthchecks fuer casg-api + pie-web (python-urllib), `depends_on`
  `condition: service_healthy` (F7).
- Per-Job ephemeres internes Netz `bhb-job-<report_id>` im docker_driver (F8).
- Dead-Letter-Queue `queue:realtime:dead` im Broker (F10).

### Geaendert
- DB-Connection-Leak behoben: `with closing(db()) ...` in casg-api app.py
  (health/submit/_set_status), broker.py persist_verdict, relay worker.py
  report_meta. psycopg2-Connections werden jetzt geschlossen (F1).
- seccomp angewandt: docker_driver liest `SECCOMP_PROFILE` (/etc/bhb/seccomp.json,
  Bind aus compose) und uebergibt Inline-JSON als `security_opt` an Runner;
  fehlt Datei -> graceful skip (F2).
- Runner Wall-Clock: `container.kill()` nach wait-Timeout vor remove (F4-Driver).
- traefik-Dashboard: `--api.insecure=true` entfernt, Port-Publish auf
  `127.0.0.1:6088`, BasicAuth-Middleware `dashboard-auth` (F6).
- scan.py `resolve_source`: Scheme-Whitelist (nur lokaler Pfad / `org/repo` /
  https-github), `ext::/file:///git:///ssh://` + fuehrendes `-` abgelehnt,
  git mit `-c protocol.ext.allow=never -c protocol.allow=user` (F5).
- runner.py Repro-Hash via `with open(...)` (File-Handle-Leak, F11).
- V2/V3-Verdikt-Mappings als Phase-2-reserviert kommentiert (broker severity_for,
  relay LABEL); Verhalten unveraendert (F12).
- gate.py: unbekannte/leere `bug_class` -> `unknown_bug_class` reject (F9).

### Behoben
- F1 DB-Connection-Leak (P0), F4 Runner-Wall-Clock unbegrenzt (P1),
  F5 git-clone ext::-RCE (P2), F7 Health 200 bei Fehler (P2),
  F9 unbekannte bug_class -> Tier A (P3), F10 Malformed-Job stiller Verlust (P3),
  F11 File-Handle-Leak Runner (P3).

### Verifiziert
- pytest: casg-api 13 passed, csve-broker 23 passed, pie-scanner 12 passed;
  csve-runner Logik unter sh verifiziert (Modul-Skip auf win32).
- `docker compose config -q` OK, `py_compile` der geaenderten Module OK.

## [0.4.0] - 2026-06-25

### Hinzugefuegt
- Linux-Deploy-Skripte unter `deploy/`: `00_prereqs.sh` (Docker/Compose/openssl/
  iptables-Check), `01_bootstrap.sh` (.env aus Vorlage + `openssl rand`-Secrets,
  chmod 600, harter Stopp bei Rest-Platzhalter `change-me-strong`),
  `02_deploy.sh` (Build Kern + Runner-Image build-only, `up -d`, Health-Wait,
  `host-firewall.sh`-Airgap), `03_teardown.sh` (`--purge`-Option),
  `deploy.sh` (Wrapper), `bhb.service` (systemd-Boot-Start), `deploy/README.md`.

### Verifiziert
- `bash -n` aller Deploy-Skripte fehlerfrei.

## [0.3.3] - 2026-06-14

### Hinzugefuegt
- Pflicht-Doku-Dateien INFRA.md, MVC.md, ERKLAERUNG.md angelegt und befuellt
  (globale Doku-Trias §6.5).

### Geaendert
- .gitignore: `z_old/` -> `z_*`; `*.md`-Ausschluss mit Whitelist
  (CHANGELOG/README*/LICENSE/BLUEPRINT). Interne Doku (INFRA/MVC/ERKLAERUNG,
  Plaene, Konzepte, TODOs) bleibt lokal, nicht auf GitHub.

### Verifiziert
- git check-ignore: INFRA/MVC/ERKLAERUNG/LICENSE_TODO ignoriert;
  README/README_EN/CHANGELOG/LICENSE/BLUEPRINT nicht ignoriert.

## [0.3.2] - 2026-06-14

### Hinzugefuegt
- README_EN.md: englische Uebersetzung der README. Enthaelt Translation-Sync-
  Hinweis (Stand-Datum der deutschen Quelle) zur Erkennung veralteter
  Uebersetzung.
- Datums-Block (Erstellt/Stand bzw. Created/Updated) direkt unter H1 in beiden
  READMEs. Divergenz deutsch/englisch ueber Datumsvergleich sichtbar.

### Geaendert
- README.md: Sprach-Link auf README_EN.md ganz oben.

## [0.3.1] - 2026-06-14

Lizenzwechsel MIT -> AGPL-3.0. Copyleft mit Netzwerk-Klausel (§13) schuetzt
gegen Closed-Source-Kommerzialisierung als gehosteter Dienst ohne Quellcode-
Freigabe und ohne Attribution.

### Hinzugefuegt
- LICENSE.md: AGPL-3.0 Volltext, ausgefuellter Notice-Block
  (Copyright 2026 Nope-im-not-pro).
- AGPL §5a Lizenz-Header in 11 Source- + 6 Test-Modulen (services/*).
- form.html: §13 Source-Link + Appropriate Legal Notices (Footer:
  Copyright, AGPL-Link, Source-Link, Gewaehrleistungsausschluss).
- LICENSE_TODO.md: Konformitaets-Checkliste.
- OCI-Image-Labels in 6 Dockerfiles (org.opencontainers.image.title/
  licenses=AGPL-3.0-or-later/source/authors).

### Geaendert
- README.md Lizenz-Sektion: MIT -> AGPL-3.0 inkl. Copyleft-/SaaS-Hinweis.

### Verifiziert
- pytest casg-api/pie-scanner/csve-broker: 29 passed (Header sind Kommentare,
  keine Logik-Aenderung).

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
- Image-Build/Provisionierung/Airgap (Akzeptanz 1-4) NICHT verifiziert -
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
