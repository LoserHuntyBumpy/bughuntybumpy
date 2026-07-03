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

---

## VM-Alternative (UMSETZUNGSPLAN_VM-Alternative_2026-06-12 v1.1)

Code-Generierung lokal (CLAUDE.md §5.8: Quellcode bleibt Claude).

- [x] Phase 0 - gitignore + vm/-Geruest
      path:   claude:scaffold
      result: .gitignore um vhdx/qcow2/seed.iso/tf-state ergaenzt. vm/{packer,cloudinit,terraform,ansible,scripts} angelegt
- [x] Phase 3a - Broker-Entkopplung (verhaltenserhaltend Docker)
      path:   claude:refactor-regression-safe
      result: runner_driver.py (Interface+Factory), docker_driver.py (lazy import docker, run_job/ensure_networks/_parse_verdict 1:1), broker.py ohne docker-Modul-Import, Dispatch RUNNER_BACKEND, check_combo gesperrte Kombi
- [x] Phase 3a - Regressionstest Docker-Pfad
      path:   claude:pytest
      result: test_broker.py broker-seitig + test_docker_driver.py driver-seitig. Assertions erhalten. 20 broker-tests passed
- [x] Phase 3b - vm_driver (hyperv|libvirt)
      path:   claude:feature
      result: spawn() Seed-ISO+Lifecycle-Skript+Verdikt-Datei+try/finally cleanup, sweep_orphans. test_vm_driver.py: spawn/timeout/error/no-verdict/parse-error/bad-backend
- [x] Phase 1 - Packer Golden+5 Rollen
      path:   claude:infra-scaffold
      result: base-debian12 (hyperv-iso+qemu, snapshot-pin), role-ingress/app/data/broker/runner (vmcx/backing-clone). IMAGES.lock-Platzhalter
- [x] Phase 2 - cloud-init + Terraform + Ansible
      path:   claude:infra-scaffold
      result: cloudinit 5 (runner: read-only-root/tmpfs/kein-routing). terraform main/variables/outputs (profile-Gate hyperv|libvirt). ansible site.yml (data/app/broker systemd+venv, schema-init)
- [x] Phase 2/5 - Lifecycle-Skripte
      path:   claude:shell
      result: 010_build/020_provision/030_destroy, runner_spawn.ps1 (Results-VHDX-Rueckkanal), runner_spawn.sh (virtio-serial), orphan_sweep.ps1/sh, 040_airgap_verify.sh
- [x] Phase 4 - Airgap-Verifikation (Skript)
      path:   claude:shell
      result: 040_airgap_verify.sh: ICMP/DNS/HTTP/Default-Route/Lateral muessen scheitern, exit!=0 bei Leak. Reale Ausfuehrung braucht Runner-VM
- [x] Phase 5 - Doku-Trias
      path:   claude:doku
      result: BLUEPRINT_VM-Infrastruktur.md neu, README VM-Sektion+Struktur+Testzahl, CHANGELOG 0.3.0. Dockerfile Treiber-Module ergaenzt
- [x] Gesamttest
      path:   claude:pytest
      result: casg-api+pie-scanner+csve-broker 29 passed. Akzeptanz 5+6 verifiziert; 1-4 brauchen Hyper-V/Packer/TF-Toolchain (Phase 0)

---

## FixPlan-Umsetzung (FixPlan_2026-06-25, 3 Opus-Agents parallel)

Orchestrator verteilt disjunkte Datei-Ownership, Reviewer-Sign-off zentral.
Agent A: casg-api/pie-web/compose. Agent B: broker/driver/relay. Agent C: runner/scanner.

- [x] F1 DB-Connection-Leak (P0)
      path:   claude:agentA+agentB
      result: closing(db()) in app.py/broker.py/worker.py. psycopg2-conn schliesst jetzt
- [x] F2 seccomp-Profil angewandt (P1)
      path:   claude:agentA+agentB
      result: driver liest SECCOMP_PROFILE inline-JSON -> security_opt. compose bind+env. graceful skip
- [x] F4 Runner Wall-Clock + Step-Cap (P1)
      path:   claude:agentB+agentC
      result: runner MAX_STEPS=50 + timebox-guard. driver container.kill() nach wait-timeout
- [x] F3 Auth/Rate-Limit (P1)
      path:   claude:agentA
      result: throttle.py redis-quota 30/min/IP -> 429. traefik ratelimit+bodylimit 1MB
- [x] F5 git-clone ext::-RCE Scanner (P2)
      path:   claude:agentC
      result: scheme-whitelist, ext/file/git/ssh+leading-dash reject, protocol.ext.allow=never
- [x] F7 Health 503 + healthcheck (P2)
      path:   claude:agentA
      result: casg-api 503 bei Fehler. compose healthcheck casg/pie, depends_on service_healthy
- [x] F6 traefik-Dashboard schliessen (P2)
      path:   claude:agentA
      result: api.insecure raus, 127.0.0.1:6088 loopback, BasicAuth dashboard-auth
- [x] F8 Runner-Netz-Isolation (P2)
      path:   claude:agentB
      result: ephemeres internes bhb-job-<id> pro Job, finally net.remove. SANDBOX/HONEYPOT-Konst entfernt
- [x] F9 unknown bug_class -> reject (P3)
      path:   claude:agentA
      result: validate -> unknown_bug_class bei nicht-TIER1|2|3 (inkl. leer)
- [x] F11 File-Handle-Leak Runner (P3)
      path:   claude:agentC
      result: with open(repro_path,"rb") fuer repro_hash
- [x] F10 Malformed-Job Dead-Letter (P3)
      path:   claude:agentB
      result: queue:realtime:dead rpush bei Exception vor lrem, log mit report_id
- [x] F12 tote V2/V3-Mappings (P3)
      path:   claude:agentB
      result: Phase-2-reserviert kommentiert (broker severity_for, relay LABEL), Verhalten gleich
- [x] Reviewer-Sign-off + Gesamttest
      path:   claude:orchestrator-review
      result: 48 tests passed (13+23+12), runner sh-verifiziert, compose config -q OK

---

## Audit-Fix-Umsetzung (AUDIT_2026-07-03, F-001..F-013)

- [x] F-001 casg-api Dockerfile kopiert throttle.py
      path:   claude:dockerfile-fix
      result: COPY um throttle.py ergaenzt. Image gebaut, Container healthy, import throttle im Image OK
- [x] F-002 csve-broker Hardening (no-new-privileges, non-root USER)
      path:   claude:hardening
      result: USER broker (GID via DOCKER_GID-Build-Arg, existierende GID wiederverwendet), compose security_opt. Socket-Ping non-root OK, Spawn-Verhalten identisch root/non-root
- [x] F-003 Traefik-Dashboard Default-Hash entfernen + Bootstrap-Generierung
      path:   claude:secret-hygiene
      result: compose :?-Interpolation verweigert Start bei leer/unset. Bootstrap generiert apr1-Hash (fehlender Key wird ergaenzt). Verifiziert beide Pfade
- [x] F-004 .gitignore !INFRA.md entfernen (INFRA bleibt lokal)
      path:   claude:gitignore-fix
      result: !INFRA.md raus + git rm --cached (war getrackt). check-ignore matcht *.md. Historie auf GitHub behaelt alte Version
- [x] F-005 .gitignore vm/scripts/*.ps1 ausnehmen
      path:   claude:gitignore-fix
      result: !vm/scripts/*.ps1. runner_spawn.ps1 nicht mehr ignoriert, git_push.ps1 bleibt ignoriert
- [x] F-006 MAX_STEPS/REALTIME_TIMEBOX_SEC an Runner durchreichen
      path:   claude:config-plumbing
      result: driver environment + compose MAX_STEPS. Neuer Unit-Test test_spawn_passes_step_caps_env gruen
- [x] F-007 relay-worker Reliable-Queue (BLMOVE + dead-letter)
      path:   claude:reliability
      result: BLMOVE->processing, LREM nach Erfolg, dead-letter queue:verdicts:dead, reclaim beim Start. Muster 1:1 aus broker.py
- [x] F-008 README/README_EN Stand/Testzahl/FixPlan-Verweis
      path:   claude:doku-sync
      result: Stand/Updated 2026-07-03, 49 passed, FixPlan_2026-06-25.md. DE+EN synchron
- [x] F-009 INFRA.md Ansible-Pfad + *_token.json in .gitignore
      path:   claude:doku-fix
      result: vm/ansible/site.yml korrigiert, *_token.json ignoriert -> INFRA-Aussage jetzt wahr
- [x] F-010 throttle fail-open als Policy dokumentieren
      path:   claude:policy-decision
      result: fail-open bewusst belassen, traefik-Ratelimit erste Linie. Docstring + INFRA dokumentiert, Verhalten unveraendert
- [x] F-011 honeypot-net entfernen (compose + Doku)
      path:   claude:dead-config-cleanup
      result: Netz + Runner-Referenz raus, README/README_EN/INFRA bereinigt (ephemeres bhb-job-Netz dokumentiert)
- [x] F-012 host-firewall.sh redundante eth0-Regel entfernen
      path:   claude:shell-fix
      result: interface-unabhaengige Subnetz-Regel bleibt, eth0-Regel entfernt. bash -n OK
- [x] F-013 persist.py Exit 1 bei fehlendem psycopg2
      path:   claude:exit-code-fix
      result: sys.exit(1). Ohne psycopg2 verifiziert Exit 1, entrypoint loggt Skip
- [x] Globale Verify-Gates + Doku-Trias
      path:   claude:verify+doku
      result: pytest 49 passed 1 skipped, compose config -q OK, py_compile OK, bash -n OK. CHANGELOG 0.6.0, README/README_EN/INFRA aktualisiert. Vorbestehend offen: Broker-Workdir-Mount (Spawn->no_verdict_in_logs, separater Task), traefik-Docker-Provider-Fehler Host (BUG-1-Muster)

## D-Fix-Umsetzung (2026-07-03, D-001/D-002 aus 0.6.0-Verifikation)

- [x] D-001 Fix: repro.yml via benanntes Job-Volume statt Bind-Mount
      path:   claude:runtime-fix
      result: docker_driver: Volume bhb-job-<id> + put_archive auf nicht gestartetem Hilfscontainer (Runner-Image), Runner mountet ro. ENV-Weg verworfen (128KB-Limit pro Env-String vs 1MB Bodylimit), Shared-Volume verworfen (Job-Isolation). finally raeumt Volume+Netz+Container
- [x] D-001 Tests angepasst
      path:   claude:test-update
      result: neue Tests Volume-Transfer + repro-tar + Volume-Cleanup-on-error; Netz/seccomp/Env/Kill-Assertions erhalten. Frischer Client-Mock pro Test (Call-Akkumulation ueber Modul-Mock behoben). 26 passed
- [x] D-001 Live-Verify im Compose-Stack
      path:   claude:verify
      result: spawn expect_exit:0 -> V1, expect_exit:1 -> REJECTED. Keine bhb-job-Volumes/Netze uebrig
- [x] D-002 Diagnose Schritt 1+2: Engine-Version + Socket-Antwort
      path:   claude:diagnose
      result: Engine 29.5.3 API 1.54 (min 1.40). Socket aus alpine-Container antwortet -> Daemon-Zugriff intakt, Fehler liegt im traefik-Docker-Client
- [x] D-002 Diagnose Schritt 3: traefik-Versionstest v3.2-v3.6
      path:   claude:diagnose
      result: v3.2-v3.4 leere Daemon-Fehlermeldung, v3.5 explizit "400 Bad Request no error-message" auf /info, v3.6 liest Provider. Minimal-Bump = v3.6, kein Dateiprovider-Fallback noetig
- [x] D-002 Fix: compose traefik v3.2 -> v3.6 + Provider-Netz-Pinning
      path:   claude:config-fix
      result: v3.6 behebt Daemon-Read; danach 504 weil Provider backend-IP der Multi-Netz-Container waehlte -> providers.docker.network=bughuntybumpy_frontend. health 200, / 200 (nach Beispiel-Spec), Dashboard ohne Auth 401
- [x] Globale Verify-Gates
      path:   claude:verify
      result: compose config -q Exit 0. pytest 51 passed 1 skipped. py_compile OK. E2E: Submit via :6080/api/submit -> Broker V1, verdicts-Tabelle 1 Zeile, relay-worker loggt bhb-verified. Keine Job-Reste
- [x] Doku-Trias
      path:   claude:doku
      result: CHANGELOG 0.6.1, INFRA traefik-Zeile + Volume-Uebergabeweg, README/README_EN Testzahl 51 synchron
