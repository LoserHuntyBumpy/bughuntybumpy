# BugHuntyBumpy

Crowdsourced Bug-Bounty-Reporting-Gateway. Deterministische Verifikation ohne generative KI. 5-Layer-Architektur, Docker-Containerisierung, strikte Airgap-Sandbox fuer Closed-Shell-Replay.

---

## Was ist das?

BugHuntyBumpy (BHB) strukturiert Bug-Meldungen an Open-Source-Maintainer. Reporter liefern deterministische Reproduktions-Rezepte. BHB prueft sie automatisch in einer isolierten Sandbox. Verifizierte Reports erhalten Label + Badge auf GitHub. Zwei-Spur-Prinzip: native Issues bleiben erhalten, BHB priorisiert per Label.

Kernunterschied zu herkoemmlichen Formularen: Zwangsstruktur (Reframe-Editor + Repro-Step-Editor) filtert Zero-Effort-Meldungen. Kein Freitext als Ersatz fuer Nachvollziehbarkeit.

---

## Architektur (5 Layer)

```
Layer 1  PIE    pie-scanner: deterministische Repo-Analyse -> bughunty.yml
                 pie-web: adaptives Formular aus bughunty.yml
Layer 2  CASG   casg-api: Gate-Logik (Selftest-Pflicht, Tonalitaet, Dedup)
                 casg-web: Submission-UI (MVP: pie-web uebernimmt Submit-Proxy)
Layer 3  CSVE   csve-broker: Job-Queue-Consumer, spawnt Runner
                 csve-runner: Closed-Shell, Exit-/Output-Assertion (V1/REJECTED)
Layer 4  Trust  cert-signer: Ed25519-Validation-Certificate (MVP optional)
Layer 5  Relay  relay-worker: Verdikt -> GitHub-Label (bhb-verified, ...)
```

Netz-Trennung: frontend (traefik) / backend (internal) / sandbox (internal, kein Egress) / honeypot-net (Mock-Services).

---

## Voraussetzungen

- Docker Engine 24+ (Windows Docker Desktop / Linux Docker CE)
- Docker Compose v2+
- git
- ca. 4 GB RAM fuer den vollen Stack

---

## Schnellstart

```bash
# 1. Secrets kopieren
$ cp .env.example .env
$ # Passwoerter in .env setzen, dann speichern

# 2. Build aller Images
$ docker compose build

# 3. Kern-Stack starten
$ docker compose up -d postgres redis traefik pie-web casg-api csve-broker relay-worker

# 4. (Optional) Einmalig: Repo scannen -> bughunty.yml erzeugen
$ docker compose run --rm pie-scanner <github-org>/<repo>
# Beispiel:
$ docker compose run --rm pie-scanner eisenberglan/BugHuntyBumpy

# 5. Formular aufrufen
$ open http://localhost:6080/
```

---

## Smoke-Test

```bash
# Health-Checks
curl -fsS http://localhost:6080/api/health

# Spec erzeugen (falls Schritt 4 uebersprungen)
docker compose run --rm pie-scanner eisenberglan/BugHuntyBumpy

# Submit via curl
curl -X POST http://localhost:6080/api/submit \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "eisenberglan/BugHuntyBumpy",
    "commit": "abc123",
    "bug_class": "xss",
    "runtime": "docker",
    "env_output": "docker 29.4.3",
    "reframe": {
      "context": "BHB v0.2.0 unter Docker 29",
      "expectation": "Formular laeuft stabil",
      "reality": "404 bei Router-Discovery",
      "selftest": "traefik Port geprueft, Logs gelesen"
    },
    "repro": {
      "commit": "abc123",
      "steps": [
        {"run": "echo 1247 rows", "expect_exit": 0, "expect_output": "1247 rows"}
      ]
    },
    "proof_of_context": {}
  }'

# Broker-Logs beobachten
docker compose logs -f csve-broker
```

---

## Projektstruktur

```
BugHuntyBumpy/
├── docker-compose.yml              # Produktions-Grundgeruest
├── .env.example                    # Secrets-Vorlage
├── host-firewall.sh                # iptables Egress-Block Sandbox
├── db/init/01_schema.sql           # Postgres-Schema (SQLAlchemy-raw)
├── data/
│   ├── repos/                      # gescannte Repos (gitignored)
│   ├── repro-test/                 # Test-Rezepte
│   └── spec-test/                  # Beispiel-bughunty.yml
├── services/
    ├── pie-scanner/scan.py         # StackProfiler + SASTCluster
    ├── pie-web/app.py              # FastAPI + Jinja2 Formular
    ├── casg-api/app.py             # Submission-Gateway
    ├── casg-api/gate.py            # Gate-Service (Business-Logik)
    ├── csve-broker/broker.py       # Job-Orchestrierung
    ├── csve-runner/runner.py       # Deterministischer Verdikt-Runner
    ├── csve-runner/seccomp.json    # Syscall-Whitelist
    └── relay-worker/worker.py      # GitHub-Badge-Stub

```

---

## Sicherheit

- **Sandbox-Airgap:** `internal: true`, Host-Firewall als zweite Linie.
- **Runner-Haertung:** read-only, `cap_drop: [ALL]`, `no-new-privileges`, seccomp, pids/mem/cpu-Limits.
- **Keine KI in der Verifikation:** Deterministisch (Exit-Code + Output-Hash).
- **Secrets .gitignored:** `.env`, `secrets/`, `data/`, `letsencrypt/`.

Siehe `BLUEPRINT_Docker-Infrastruktur.md` Sektion 12 fuer vollstaendige Checkliste.

---

## Tests

```bash
# Unit-Tests aller Services (lokal, kein Docker noetig)
$ python -m pytest services/*/tests/ -v
```

Aktueller Stand: 12 passed, 1 skipped (Runner-Tests erfordern Linux-Shell).

---

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md)

---

## Lizenz

MIT (bald)
