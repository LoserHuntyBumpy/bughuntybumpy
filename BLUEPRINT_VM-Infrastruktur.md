# Blueprint: VM-Infrastruktur (Pendant zu Docker-Blueprint)

**Version:** 1.0
**Datum:** 2026-06-13
**Quelle:** UMSETZUNGSPLAN_VM-Alternative_2026-06-12.md v1.1, BLUEPRINT_Docker-Infrastruktur.md v1.0
**Status:** Code-Entkopplung + Treiber-Gerust umgesetzt; Image-Build/Provisionierung als Skript-Gerust (Host-Toolchain erforderlich).

VM-Variante als **waehlbare Alternative** zu Docker. Docker bleibt Default und
voll funktionsfaehig. Kein Ersatz, kein Bruch (Regressionsfreiheit, Plan §8/5).

---

## 1. Zwei Wahl-Achsen (Plan §3.5)

| Achse | Werte | Schalter |
|---|---|---|
| A - Stack-Deploy | `compose` (Default) \| `vm` | Provisionierungs-Skript: `docker compose up` vs. `vm/scripts/020_provision_stack.ps1` |
| B - Runner-Backend | `docker` (Default) \| `vm` | Env `RUNNER_BACKEND` in broker.py |

Gueltige Kombinationen:

| Stack | Runner | Status |
|---|---|---|
| compose | docker | Default, Ist |
| vm | vm | reine VM-Welt |
| vm | docker | zulaessig (Uebergang, nested) |
| compose | vm | **gesperrt** - Abbruch in `broker.check_combo()` |

---

## 2. Treiber-Entkopplung (Kern, umgesetzt)

broker.py kennt keine Sandbox-Technologie mehr. `import docker` liegt
ausschliesslich (lazy) in `docker_driver.py`. Dispatch via `RUNNER_BACKEND`.

```
services/csve-broker/
├── broker.py          # Queue-Consumer + Dispatch + Persistenz, KEIN docker-Import
├── runner_driver.py   # Interface RunnerDriver.spawn(report_id, repro) -> dict + Factory
├── docker_driver.py   # Ist-Docker-Logik 1:1 (lazy import docker), ensure_networks
└── vm_driver.py       # ephemere Runner-VM (hyperv | libvirt)
```

Interface-Kontrakt: `spawn()` liefert immer Verdikt-Dict (V1/V2/REJECTED),
nie Exception. Broker persistiert; Treiber kennt weder postgres noch redis.

---

## 3. Ziel-Topologie

4 Rollen-VMs (ingress/app/data/broker) + ephemere Runner-VMs. Netz-Mapping:

| Docker-Netz | VM-Switch | Eigenschaft |
|---|---|---|
| frontend | ext-switch (External/NAT) | einziger Internet-Pfad, nur ingress |
| backend | svc-switch (Internal/Host-Only) | App<->DB, kein Uplink |
| sandbox | sandbox-switch (Private) | physisch kein Egress |

---

## 4. Ephemere Runner-VM (Layer 3, Plan §5)

Ersetzt `docker run --rm csve-runner`:

1. Seed-Verzeichnis (repro.yml + meta-data) erzeugt `vm_driver._build_seed_iso`.
2. Spawn-Skript baut NoCloud-ISO (oscdimg/genisoimage), Linked Clone, attach
   nur sandbox-switch, 2 GB/2 vCPU statisch.
3. VM bootet, systemd-Unit `bhb-runner` fuehrt runner.py aus.
4. Verdikt-Rueckkanal: Hyper-V Results-VHDX (read-only gemountet) bzw.
   libvirt virtio-serial. JSON-Schema unveraendert.
5. Garantiertes Destroy (PowerShell `finally` / bash `trap EXIT`), Timebox-Kill.
6. Orphan-Sweep beim Broker-Start (`sweep_orphans()`).

Haertungs-Mapping:

| Docker | VM |
|---|---|
| read_only | Root-FS read-only (cloud-init), tmpfs-Overlay |
| mem_limit/cpus | statische VM-Konfiguration |
| internal: true | Switch ohne Uplink - kein Routing-Pfad |
| seccomp/cap_drop | VM-Kernel-Grenze + systemd TasksMax, kein sudo |
| Timebox 600 s | Watchdog: Stop-VM -TurnOff / virsh destroy |

---

## 5. Automatisierungs-Pipeline

| Werkzeug | Datei(en) | Rolle |
|---|---|---|
| Packer | `vm/packer/*.pkr.hcl` | Golden Base + 5 Rollen-Images, SHA-256 in `vm/IMAGES.lock` |
| cloud-init | `vm/cloudinit/*.yml` | First-Boot (Hostname, Netz, Service-Env, Runner read-only) |
| Terraform | `vm/terraform/*.tf` | Switches + 4 Rollen-VMs (Provider hyperv \| libvirt via `profile`) |
| Ansible | `vm/ansible/site.yml` | Service-Deploy (systemd + venv), DB-Init 01_schema.sql |
| Skripte | `vm/scripts/*.ps1/.sh` | Build/Provision/Destroy/Runner-Lifecycle/Orphan/Airgap |

Profile: `dev-windows` (Hyper-V), `prod-linux` (KVM/libvirt). Gleiche Pipeline.

---

## 6. Akzeptanz (Plan §8) - Stand

| # | Kriterium | Stand |
|---|---|---|
| 1 | 010_build_images.ps1 baut 5 Rollen-Images | Skript-Gerust (braucht Packer-Host) |
| 2 | 020_provision_stack.ps1 Stack + Health gruen | Skript-Gerust (braucht TF/Ansible-Host) |
| 3 | Submit -> Runner-VM-Spawn -> Verdikt V1 | vm_driver-Kontrakt + Lifecycle-Skripte vorhanden |
| 4 | Kein Egress, Destroy 100 % inkl. Crash | Airgap-Test-Skript + try/finally-Destroy + Orphan-Sweep |
| 5 | RUNNER_BACKEND=docker regressionsfrei | **verifiziert** (docker_driver bit-identisch, Tests gruen) |
| 6 | pytest-Suite gruen | **verifiziert** (29 passed casg/scanner/broker) |

Kriterien 1-4 erfordern reale Hyper-V/Packer/Terraform-Toolchain (Phase 0),
auf diesem Host nicht ausgefuehrt.

---

## 7. Ausserhalb Scope (Plan §9)

Firecracker/Kata, K8s/Helm, Confidential Computing, Produktiv-TLS/ACME.
