# BugHuntyBumpy

Created: 2026-06-14 | Updated: 2026-06-14
Language: English (translation) | [Deutsche Version](README.md) (original)

> Translation sync: this English version reflects the German [README.md](README.md)
> at state **2026-06-14**. If the German "Stand" date above is newer than this
> file's "Updated" date, this translation is outdated and the German original
> takes precedence.

Crowdsourced bug-bounty reporting gateway. Deterministic verification without
generative AI. 5-layer architecture, Docker containerization, strict air-gapped
sandbox for closed-shell replay.

---

## What is this?

BugHuntyBumpy (BHB) structures bug reports to open-source maintainers. Reporters
deliver deterministic reproduction recipes. BHB checks them automatically in an
isolated sandbox. Verified reports receive a label + badge on GitHub. Two-track
principle: native issues are preserved, BHB prioritizes via label.

Core difference to conventional forms: forced structure (reframe editor + repro
step editor) filters zero-effort reports. No free text as a substitute for
traceability.

---

## Architecture (5 layers)

```
Layer 1  PIE    pie-scanner: deterministic repo analysis -> bughunty.yml
                 pie-web: adaptive form from bughunty.yml
Layer 2  CASG   casg-api: gate logic (selftest requirement, tone, dedup)
                 casg-web: submission UI (MVP: pie-web handles submit proxy)
Layer 3  CSVE   csve-broker: job-queue consumer, spawns runner
                 csve-runner: closed shell, exit/output assertion (V1/REJECTED)
Layer 4  Trust  cert-signer: Ed25519 validation certificate (MVP optional)
Layer 5  Relay  relay-worker: verdict -> GitHub label (bhb-verified, ...)
```

Network separation: frontend (traefik) / backend (internal) / sandbox (internal,
no egress) / honeypot-net (mock services).

---

## Requirements

- Docker Engine 24+ (Windows Docker Desktop / Linux Docker CE)
- Docker Compose v2+
- git
- approx. 4 GB RAM for the full stack

---

## Quick start

```bash
# 1. Copy secrets
$ cp .env.example .env
$ # set passwords in .env, then save

# 2. Build all images
$ docker compose build

# 3. Start core stack
$ docker compose up -d postgres redis traefik pie-web casg-api csve-broker relay-worker

# 4. (Optional) one-time: scan repo -> generate bughunty.yml
$ docker compose run --rm pie-scanner <github-org>/<repo>
# Example:
$ docker compose run --rm pie-scanner eisenberglan/BugHuntyBumpy

# 5. Open the form
$ open http://localhost:6080/
```

---

## Smoke test

```bash
# Health checks
curl -fsS http://localhost:6080/api/health

# Generate spec (if step 4 was skipped)
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
      "context": "BHB v0.2.0 on Docker 29",
      "expectation": "Form runs stable",
      "reality": "404 on router discovery",
      "selftest": "checked traefik port, read logs"
    },
    "repro": {
      "commit": "abc123",
      "steps": [
        {"run": "echo 1247 rows", "expect_exit": 0, "expect_output": "1247 rows"}
      ]
    },
    "proof_of_context": {}
  }'

# Observe broker logs
docker compose logs -f csve-broker
```

---

## Project structure

```
BugHuntyBumpy/
|-- docker-compose.yml              # production scaffold
|-- .env.example                    # secrets template
|-- host-firewall.sh                # iptables egress block for sandbox
|-- db/init/01_schema.sql           # Postgres schema (SQLAlchemy raw)
|-- data/
|   |-- repos/                      # scanned repos (gitignored)
|   |-- repro-test/                 # test recipes
|   `-- spec-test/                  # example bughunty.yml
|-- services/
|   |-- pie-scanner/scan.py         # StackProfiler + SASTCluster
|   |-- pie-web/app.py              # FastAPI + Jinja2 form
|   |-- casg-api/app.py             # submission gateway
|   |-- casg-api/gate.py            # gate service (business logic)
|   |-- csve-broker/broker.py       # job orchestration + driver dispatch
|   |-- csve-broker/runner_driver.py# driver interface + factory (docker|vm)
|   |-- csve-broker/docker_driver.py# Docker backend (lazy import docker)
|   |-- csve-broker/vm_driver.py    # VM backend (hyperv|libvirt)
|   |-- csve-runner/runner.py       # deterministic verdict runner
|   |-- csve-runner/seccomp.json    # syscall whitelist
|   `-- relay-worker/worker.py      # GitHub badge stub
|-- vm/                             # VM profile (alternative to Docker)
|   |-- packer/                     # golden base + 5 role images
|   |-- cloudinit/                  # first-boot provisioning
|   |-- terraform/                  # switches + role VMs (hyperv|libvirt)
|   |-- ansible/site.yml            # service deploy (systemd + venv)
|   |-- scripts/                    # build/provision/destroy/runner-lifecycle
|   `-- IMAGES.lock                 # image hashes (env_hash contract)
`-- BugFixPlan_2026-06-09.md        # archived planning
```

---

## Security

- **Sandbox air-gap:** `internal: true`, host firewall as second line.
- **Runner hardening:** read-only, `cap_drop: [ALL]`, `no-new-privileges`, seccomp, pids/mem/cpu limits.
- **No AI in verification:** deterministic (exit code + output hash).
- **Secrets gitignored:** `.env`, `secrets/`, `data/`, `letsencrypt/`.

See `BLUEPRINT_Docker-Infrastruktur.md` section 12 for the full checklist.

---

## Tests

```bash
# Unit tests for all services (local, no Docker needed)
$ python -m pytest services/*/tests/ -v
```

Current state: 29 passed (casg-api, pie-scanner, csve-broker incl.
docker_driver + vm_driver). Runner tests require a Linux shell.

---

## VM profile (alternative to Docker)

Container OR VM selectable at runtime. Docker stays the default. Two axes:

- **Stack deploy** (`STACK=compose|vm`): how the overall stack runs.
- **Runner backend** (`RUNNER_BACKEND=docker|vm`): how a layer-3 job is executed.

Locked: `STACK=compose` + `RUNNER_BACKEND=vm` (a broker inside a container cannot
drive the host hypervisor) - broker.py aborts hard at startup.

```powershell
# Profile: dev-windows (Hyper-V) | prod-linux (KVM/libvirt)
# 1. Build golden + role images (SHA-256 -> vm/IMAGES.lock)
vm\scripts\010_build_images.ps1 -Profile dev-windows
# 2. Provision stack (terraform apply + ansible), health check
vm\scripts\020_provision_stack.ps1 -Profile dev-windows
# 3. Teardown
vm\scripts\030_destroy_stack.ps1 -Profile dev-windows
```

Switch only the runner backend (stack stays Docker, broker VM-capable):
`RUNNER_BACKEND=vm VM_BACKEND=hyperv` in the broker env. Details:
[BLUEPRINT_VM-Infrastruktur.md](BLUEPRINT_VM-Infrastruktur.md).

VM profile prerequisites: Hyper-V (Windows) or KVM/libvirt (Linux), Packer,
Terraform, Ansible (WSL2 on Windows). See plan phase 0.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

---

## License

GNU Affero General Public License v3.0 (AGPL-3.0). Full text: [LICENSE.md](LICENSE.md).

Copyright (C) 2026  <Nope-im-not-pro> <nope-im-not-pro@keemail.me>

Copyleft with network clause (AGPL section 13): anyone who modifies BugHuntyBumpy
and operates it as a network service must make the source code of the running
version available to all users. Commercial use is permitted, but only while
preserving the license, the copyright notice, and the disclosure obligation.
Closed-source exploitation without source release is a license violation.

SaaS note: a publicly reachable BHB instance must offer a "Source" link to the
code archive in the web UI (AGPL section 13).
