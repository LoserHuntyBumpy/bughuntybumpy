# PROCESS_STEPS - BHB MVP-Umsetzung (Konzept v4 / Blueprint v1.0)

Quelle: BLUEPRINT_Docker-Infrastruktur.md, Konzept4_Master-Fusion.md §9 Phase 1.
Scope: Container-Automatisierung + Formular + GitHub-Repo-Analyse-Script.

- [x] Repo-Geruest + Infra-Wurzel
      path:   claude:infra-scaffold
      result: docker-compose.yml, .env.example, .gitignore, host-firewall.sh, db/init/01_schema.sql angelegt
- [x] L1 pie-scanner (GitHub-Repo-Analyse -> bughunty.yml)
      path:   claude:deterministic-no-ai
      result: scan.py StackProfiler/SurfaceMapper/DependencyMiner/TestEnv/SAST. Lokal verifiziert exit0, deterministisch
- [x] L1 pie-web (Formular aus bughunty.yml gerendert)
      path:   claude:view-layer
      result: FastAPI+Jinja, Verhaltenskodex-Gate, Reframe-Editor, Repro-Step-Editor, Proof-of-Context, JS-Submit
- [x] L2 casg-api (Gate-Logik, Repro-Intake, Job-Push)
      path:   claude:controller+service-split
      result: gate.py Selftest-Pflicht/Ad-Hominem-Tonalitaet/repro_class/dedup-hash. Verifiziert: emotional vs security-neutral
- [x] L3 csve-broker (Job-Consumer, Runner-Provisionierung)
      path:   claude:mvp-python-statt-go
      result: BLPOP queue:realtime, docker-SDK spawnt ephemeren read-only/cap-drop Runner, Verdikt->postgres, notify
- [x] L3 csve-runner (Closed-Shell, Exit-Code-Assertion)
      path:   claude:deterministic-no-ai
      result: runner.py Exit/Output-Assertion, erster Mismatch beendet. Verifiziert V1-pass + REJECTED-fail
- [x] L5 relay-worker (GitHub-Badge-Stub)
      path:   claude:stub
      result: queue:verdicts->Label-Mapping V1=bhb-verified usw., Output-Paket, GitHub-Call Stub ohne App-Key
- [x] Doku-Trias
      path:   claude:regel-6-keine-stille-anlage
      result: README/CHANGELOG fehlen, nicht angelegt (§6 Anlage nur auf Auftrag). Setup in BLUEPRINT §9 vorhanden

## Abweichungen vom Blueprint (dokumentiert)
- csve-broker: Python statt Go (MVP-Reduktion, Blueprint §2/§8 Go-Worker bleibt Phase-2-Ziel).
- csve-runner: slim Python statt docker:dind-rootless. Exit-/Output-Assertion ohne DinD/Nix/Firecracker (Konzept §9 Phase1, eBPF/microVM Phase2).
- cert-signer/honeypot-mock/minio: nicht im MVP-Pfad, via compose-profile "full"/"scan" optional.
- traefik: nur :80 (web), kein ACME/TLS lokal. PathPrefix-Routing statt Host-Vhosts fuer lokalen Smoke-Test.

## Smoke-Test
    cp .env.example .env
    docker compose build
    docker compose run --rm pie-scanner <org/repo>      # erzeugt bughunty-spec Volume
    docker compose up -d postgres redis casg-api csve-broker relay-worker pie-web traefik
    # Formular: http://localhost/  (pie-web)  -> Submit -> casg-api -> broker -> runner -> verdict
    docker compose logs -f csve-broker relay-worker

## Smoke-Test-Lauf 2026-06-05 (Docker 29.4.3 / Compose v5.1.4)
- [x] Build aller 6 Images (default + profile scan/build-only)
      path:   claude:smoke
      result: relay-worker/casg-api/csve-broker/pie-web/pie-scanner/bhb-csve-runner gebaut, exit0
- [x] Kern-Stack up (7 Container)
      path:   claude:smoke
      result: postgres+redis healthy, casg-api/pie-web uvicorn up, broker consuming queue:realtime, relay consuming queue:verdicts
- [x] casg-api Gate + Submit
      path:   claude:smoke
      result: Class-A xss accepted, tone neutral, queued. 422 nur ohne Content-Type-Header (Client-Fehler, kein Bug)
- [x] csve-runner isoliert (pass+fail)
      path:   claude:smoke
      result: repro.yml->V1 deterministic, repro-fail.yml->REJECTED. Exit0/Exit1 korrekt, output-hash-assert greift
- [x] relay-worker Verdict-Mapping
      path:   claude:smoke
      result: queue:verdicts->Label bhb-rejected, Output-Paket gerendert, GitHub-Call Stub (kein App-Key)

### Smoke-Test Defekte (3, NICHT gefixt - ausserhalb Auftrag "Smoke-Test ausfuehren")
- BUG-1 traefik: traefik:v3.1 kann Docker-29-Daemon nicht lesen ("Error response from daemon" leer).
  Ingress :80 liefert 404, Router-Discovery tot. pie-web/casg-api nur intern erreichbar.
- BUG-2 netze: sandbox/honeypot-net nur von csve-runner (profile build-only) referenziert -> Compose
  legt Netze nie an. Broker-Runner-Spawn scheitert "network bughuntybumpy_sandbox not found".
  Smoke-Workaround: Netze manuell via `docker network create --internal` angelegt.
- BUG-3 broker remove-race: broker.py containers.run(remove=True) -> unter Docker 29 Container weg
  bevor SDK Logs/json liest -> "No such container .../json: Not Found". Runner selbst korrekt (s.o.),
  nur Broker-Log-Abruf race-t. Fix: detach+wait+logs+explizit remove ODER auto_remove vermeiden.

### Verifiziert funktional
casg-api Gate, csve-runner Assertion (V1/REJECTED), relay-worker Mapping, postgres-Persistenz,
redis-Queues realtime/verdicts. End-to-End blockiert nur durch BUG-2 (umgangen) + BUG-3 (offen).

---

## BugFix-Umsetzung (BugFixPlan_2026-06-09_Final)

- [x] BUG-1 traefik Router-Discovery (v3.2 + Prioritaet)
      path:   claude:infra-fix
      result: Image v3.2 + casgapi.priority=100/pie.priority=1. Backup: .backups/...docker-compose.yml.200259.bak
- [x] BUG-2 ensure_networks in broker.py
      path:   claude:broker-fix
      result: SDK-idempotente Netz-Anlage vor Consume-Loop. docker.errors.NotFound abgefangen
- [x] BUG-3 broker remove-race + LEAK-1 cleanup + DEF-5 entfernen
      path:   claude:broker-fix
      result: detach+wait+finally remove, shutil.rmtree(workdir). ContainerError-Block entfernt
- [x] DEF-8 BLMOVE Queue-ACK + reclaim_processing
      path:   claude:broker-fix
      result: BLMOVE statt BLPOP, processing-Queue, rpoplpush reclaim bei Restart. LREM auf raw bytes
- [x] DEF-4 runner.py shell=True -> [sh,-c,cmd]
      path:   claude:runner-fix
      result: shell=False mit argv-Liste. Shell-Features erhalten (Pipes). Backup: .backups/...runner.py.200259.bak
- [x] DEF-6 scan.py _section json.loads + try/except
      path:   claude:scanner-fix
      result: Bracket-Counting ersetzt durch json.loads. import json fehlte, nachtraeglich ergaenzt
- [x] DEF-7 scan.py git-clone timeout=120
      path:   claude:scanner-fix
      result: subprocess.run(timeout=120). Backup: .backups/...scan.py.200259.bak
- [x] DEF-9 BLUEPRINT MVP-Reduktion TLS ergaenzen
      path:   claude:doku-fix
      result: Hinweis TLS/ACME auskommentiert fuer lokalen Test. Backup: .backups/...BLUEPRINT...
- [x] DEF-8 Idempotenz: UNIQUE(report_id) + ON CONFLICT DO NOTHING
      path:   claude:review-fix
      result: Schema + broker.py persist_verdict idempotent. Backup: .backups/...201534.bak
- [x] Broker-Tests erweitern (ensure_networks, reclaim, persist_idempotent, timebox, cleanup)
      path:   claude:review-fix
      result: 18 passed, 1 skipped. test_broker.py 9 Tests
- [x] BUG-1 Diagnose: --api.insecure=true in traefik command
      path:   claude:review-fix
      result: http://localhost:6088/api/rawdata verfuegbar fuer Diagnose
- [x] CHANGELOG korrigiert (nicht Behoben vor Verifikation)
      path:   claude:review-fix
      result: Sektion "In Arbeit / Behoben (Code + teilweise verifiziert)"
