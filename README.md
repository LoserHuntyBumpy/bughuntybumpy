# BugHuntyBumpy

Erstellt: 2026-06-14 | Stand: 2026-07-03
Sprache: Deutsch (Original) | [English version](README_EN.md)

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

Netz-Trennung: frontend (traefik) / backend (internal) / sandbox (internal, kein Egress). Pro Job zusaetzlich ephemeres internes Netz `bhb-job-<id>`.

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
│   ├── pie-scanner/scan.py         # StackProfiler + SASTCluster
│   ├── pie-web/app.py              # FastAPI + Jinja2 Formular
│   ├── casg-api/app.py             # Submission-Gateway
│   ├── casg-api/gate.py            # Gate-Service (Business-Logik)
│   ├── csve-broker/broker.py       # Job-Orchestrierung + Treiber-Dispatch
│   ├── csve-broker/runner_driver.py# Treiber-Interface + Factory (docker|vm)
│   ├── csve-broker/docker_driver.py# Docker-Backend (lazy import docker)
│   ├── csve-broker/vm_driver.py    # VM-Backend (hyperv|libvirt)
│   ├── csve-runner/runner.py       # Deterministischer Verdikt-Runner
│   ├── csve-runner/seccomp.json    # Syscall-Whitelist
│   └── relay-worker/worker.py      # GitHub-Badge-Stub
├── vm/                             # VM-Profil (Alternative zu Docker)
│   ├── packer/                     # Golden Base + 5 Rollen-Images
│   ├── cloudinit/                  # First-Boot-Provisionierung
│   ├── terraform/                  # Switches + Rollen-VMs (hyperv|libvirt)
│   ├── ansible/site.yml            # Service-Deploy (systemd + venv)
│   ├── scripts/                    # build/provision/destroy/runner-lifecycle
│   └── IMAGES.lock                 # Image-Hashes (env_hash-Kontrakt)
└── FixPlan_2026-06-25.md           # Archivierte Planung
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

Aktueller Stand: 51 passed (casg-api inkl. throttle, pie-scanner, csve-broker
inkl. docker_driver + vm_driver). Runner-Tests erfordern Linux-Shell
(Modul-Skip auf win32).

---

## VM-Profil (Alternative zu Docker)

Container ODER VM zur Laufzeit waehlbar. Docker bleibt Default. Zwei Achsen:

- **Stack-Deploy** (`STACK=compose|vm`): wie laeuft der Gesamt-Stack.
- **Runner-Backend** (`RUNNER_BACKEND=docker|vm`): wie wird Layer-3-Job ausgefuehrt.

Gesperrt: `STACK=compose` + `RUNNER_BACKEND=vm` (Broker im Container kann
Host-Hypervisor nicht treiben) - broker.py bricht beim Start hart ab.

```powershell
# Profile: dev-windows (Hyper-V) | prod-linux (KVM/libvirt)
# 1. Golden + Rollen-Images bauen (SHA-256 -> vm/IMAGES.lock)
vm\scripts\010_build_images.ps1 -Profile dev-windows
# 2. Stack provisionieren (terraform apply + ansible), Health-Check
vm\scripts\020_provision_stack.ps1 -Profile dev-windows
# 3. Abbau
vm\scripts\030_destroy_stack.ps1 -Profile dev-windows
```

Runner-Backend nur umschalten (Stack bleibt Docker, Broker-VM-fähig):
`RUNNER_BACKEND=vm VM_BACKEND=hyperv` in der Broker-Env. Details:
[BLUEPRINT_VM-Infrastruktur.md](BLUEPRINT_VM-Infrastruktur.md).

Voraussetzung VM-Profil: Hyper-V (Windows) bzw. KVM/libvirt (Linux), Packer,
Terraform, Ansible (WSL2 auf Windows). Siehe Plan Phase 0.

---

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md)

---

## Lizenz

GNU Affero General Public License v3.0 (AGPL-3.0). Volltext: [LICENSE.md](LICENSE.md).

Copyright (C) 2026  &lt;Nope-im-not-pro&gt; &lt;nope-im-not-pro@keemail.me&gt;

Copyleft mit Netzwerk-Klausel (AGPL §13): wer BugHuntyBumpy modifiziert und
als netzbasierten Dienst betreibt, muss den Quellcode der laufenden Version
allen Nutzern zugaenglich machen. Kommerzielle Nutzung erlaubt, aber nur unter
Erhalt von Lizenz, Copyright-Vermerk und Offenlegungspflicht. Closed-Source-
Weiterverwertung ohne Quellcode-Freigabe ist eine Lizenzverletzung.

SaaS-Hinweis: Eine oeffentlich erreichbare BHB-Instanz muss in der Web-UI
einen "Source"-Link auf das Code-Archiv anbieten (AGPL §13).
