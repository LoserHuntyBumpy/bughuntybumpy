# INFRA

Erstellt: 2026-06-14 | Stand: 2026-06-14

Hosting, Deploy, Ports, Netze, Cron, Secrets fuer BugHuntyBumpy. Interne
Doku (gitignored via `*.md`), nicht auf GitHub.

---

## Laufzeit-Modelle

Zwei Achsen, zur Laufzeit waehlbar:

- `STACK=compose|vm` - wie der Gesamt-Stack laeuft (Default: compose).
- `RUNNER_BACKEND=docker|vm` - wie Layer-3-Jobs ausgefuehrt werden (Default: docker).
- Gesperrt: `STACK=compose` + `RUNNER_BACKEND=vm` (Broker im Container kann
  Host-Hypervisor nicht treiben) -> `broker.check_combo()` bricht hart ab.

---

## Compose-Stack (Default)

Orchestrierung: `docker-compose.yml`.

| Dienst | Rolle | Port (Host) |
|---|---|---|
| traefik | Reverse-Proxy, frontend-Eintritt | 6080 (HTTP) |
| pie-web | View + Submit-Proxy (FastAPI/Jinja2) | via traefik |
| casg-api | Submission-Gateway (FastAPI) | 8000 (intern) |
| csve-broker | Job-Consumer, Runner-Dispatch | - |
| csve-runner | Closed-Shell-Verdikt-Runner | - (ephemer) |
| relay-worker | Verdikt -> GitHub-Label | - |
| postgres | Persistenz (projects, reports, verdicts) | intern |
| redis | Job-Queue (queue:realtime, queue:verdicts) | intern |

Start Kern-Stack:
```bash
docker compose up -d postgres redis traefik pie-web casg-api csve-broker relay-worker
```

---

## Netz-Trennung

| Netz | Eigenschaft |
|---|---|
| frontend | traefik-Eintritt, oeffentlich erreichbar |
| backend | `internal`, Service-zu-Service |
| sandbox | `internal: true`, KEIN Egress (Airgap fuer Runner) |
| honeypot-net | Mock-Services, Koeder |

Zweite Verteidigungslinie: `host-firewall.sh` (iptables Egress-Block fuer
Sandbox-Subnetz).

---

## VM-Profil (Alternative)

Provisionierung ueber `vm/`:
- Packer: Golden Base + 5 Rollen-Images (SHA-256 -> `vm/IMAGES.lock`).
- cloud-init: First-Boot-Provisionierung.
- Terraform: Switches + Rollen-VMs (`hyperv` | `libvirt` via Profile).
- Ansible: `vm/site.yml` (systemd + venv).
- Lifecycle-Skripte: `010_build` / `020_provision` / `030_destroy` /
  `runner_spawn` / `orphan_sweep` / `040_airgap`.

Profile: `dev-windows` (Hyper-V), `prod-linux` (KVM/libvirt).
Voraussetzung: Hyper-V bzw. KVM/libvirt, Packer, Terraform, Ansible
(WSL2 auf Windows).

Runner-Backend isoliert umschalten (Stack bleibt Docker):
`RUNNER_BACKEND=vm VM_BACKEND=hyperv` in Broker-Env.

---

## Secrets

- `.env` (Kopie aus `.env.example`) - Passwoerter, Tokens.
- `secrets/`, `letsencrypt/` - gitignored.
- Niemals committen (`.gitignore` deckt `.env`, `secrets/`, `*_token.json`).

---

## Cron / geplante Jobs

Aktuell keine. Orphan-VM-Sweep (`vm/scripts/orphan_sweep`) bei VM-Profil
manuell oder per externem Scheduler anstossen.

---

## §13-Pflicht (AGPL)

Oeffentlich erreichbare Instanz: "Source"-Link in pie-web-UI auf
Code-Archiv (umgesetzt in `services/pie-web/templates/form.html`).
