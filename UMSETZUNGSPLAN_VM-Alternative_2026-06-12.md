# Umsetzungsplan: VM-Infrastruktur als waehlbare Alternative zu Docker

**Version:** 1.1
**Datum:** 2026-06-12
**Quelle:** BLUEPRINT_Docker-Infrastruktur.md v1.0, docker-compose.yml (MVP-Stand)
**Ziel:** Container ODER VM zur Laufzeit waehlbar. Docker-Variante bleibt
voll funktionsfaehig und Default. VM-Variante wird vollautomatisiert
erstellt (Image-Build + Provisionierung + Netz). Kein Ersatz, kein Bruch.

**Aenderung v1.0 -> v1.1:** Interferenz-Pruefung gegen Ist-Code ergaenzt
(§1.5). broker.py-Entkopplung als Pflicht-Schritt (Phase 3). Wahlmodell
mit zwei Achsen explizit (§3.5). Regressionsfreiheit als hartes Kriterium.

---

## 1.5 Interferenz-Pruefung (Docker-Workflow)

Geprueft: bricht VM-Einfuehrung den bestehenden Docker-Pfad?

| Artefakt | Interferenz | Befund |
|---|---|---|
| `docker-compose.yml` | keine | VM-Deploy ist Parallelpfad, Datei unangetastet |
| `services/csve-runner/runner.py` | keine | reine subprocess-Logik, laeuft identisch in Container ODER VM |
| `services/*` (uebrig) | keine | identischer Code, nur Deploy-Schicht differiert |
| `services/csve-broker/broker.py` | **ja, real** | Modul-Ebene `import docker` + `docker.from_env()` + `ensure_networks()` |

**Bruchstelle broker.py:** Aktuell bindet broker.py Docker hart auf
Modul-Ebene (`import docker` Zeile 18, `dcli = docker.from_env()` Zeile 36,
`ensure_networks()` im `main()`). Eine naive VM-Zweig-Ergaenzung wuerde:
1. auf VM-only-Hosts ohne `docker`-Python-Paket beim Import crashen,
2. `ensure_networks()` (Docker-API) auch im VM-Modus aufrufen -> Fehler.

**Konsequenz:** broker.py MUSS auf ein Treiber-Interface umgebaut werden,
bevor der VM-Pfad zugeschaltet wird (Phase 3). Docker-Logik wandert
unveraendert hinter `docker_driver.py`, Import wird lazy. Damit bleibt der
Docker-Pfad verhaltensgleich (Regressionsfreiheit, §8 Kriterium 5).

Fazit: Docker wird nicht eliminiert. Einzige Anpassung ist die
Treiber-Entkopplung in broker.py; sie ist verhaltenserhaltend fuer Docker.

---

## 1. Motivation / Abgrenzung

| Kriterium | Docker (Ist) | VM (Soll) |
|---|---|---|
| Isolation csve-runner | Namespace + seccomp + cap_drop | Hardware-Virtualisierung (eigener Kernel) |
| Kernel-Exploit-Flaeche | geteilter Host-Kernel | pro VM eigener Kernel, Hypervisor-Grenze |
| Egress-Block | `internal: true` + iptables DOCKER-USER | Hypervisor-Switch ohne Uplink (physisch kein Pfad) |
| Startzeit Runner | ~1 s | ~5-20 s (Linked Clone / Snapshot-Restore) |
| Ressourcen-Overhead | gering | ~0.5-1 GB RAM pro VM zusaetzlich |
| Hostile-Reporter-Risiko | Container-Escape moeglich (CVE-Klasse runc/kernel) | VM-Escape deutlich seltener |

Hauptgewinn: Layer 3 (CSVE-Sandbox). Blueprint §11 nennt Firecracker/Kata als
Phase-2-Hook — dieser Plan ist die generalisierte VM-Variante davon, plus
VM-Betrieb der uebrigen Layer.

---

## 2. Ziel-Topologie (VM-Mapping)

Konsolidierung: nicht 1 Service = 1 VM, sondern 4 Rollen-VMs + ephemere Runner-VMs.

```
                         INTERNET
                            │
                  ┌─────────┴─────────┐
                  │  vm-ingress       │  nginx/traefik (TLS, Routing)
                  │  2 vCPU / 2 GB    │  Netz: ext + svc
                  └─────────┬─────────┘
                            │ svc-net (host-only / internal switch)
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  ┌───────────┐      ┌────────────┐      ┌────────────┐
  │ vm-app    │      │ vm-data    │      │ vm-broker  │
  │ pie-web   │      │ postgres   │      │ csve-broker│
  │ casg-api  │      │ redis      │      │ (spawnt    │
  │ relay-    │      │ minio      │      │  Runner-   │
  │ worker    │      │            │      │  VMs)      │
  │ 2vCPU/4GB │      │ 2vCPU/4GB  │      │ 2vCPU/2GB  │
  └───────────┘      └────────────┘      └─────┬──────┘
                                               │ control only (SSH/API)
  ═════════════════════════════════════════════╪══════  sandbox-switch (kein Uplink)
                                               ▼
                                    ┌────────────────────┐     ┌──────────────┐
                                    │ vm-runner-<jobid>  │◄───►│ vm-honeypot  │
                                    │ ephemer, Linked-   │     │ Mock-Dienste │
                                    │ Clone, autodestroy │     │ (optional)   │
                                    │ 2vCPU/2GB          │     └──────────────┘
                                    └────────────────────┘
```

**Netz-Regeln (Mapping docker-network → Hypervisor-Switch):**

| Docker-Netz | VM-Aequivalent | Eigenschaft |
|---|---|---|
| `frontend` | `ext-switch` (External/NAT) | einziger Internet-Pfad, nur vm-ingress |
| `backend` | `svc-switch` (Internal/Host-Only) | kein Uplink, App↔DB |
| `sandbox` | `sandbox-switch` (Private, kein Host-Adapter) | physisch kein Egress-Pfad |
| `honeypot-net` | gleicher `sandbox-switch`, eigenes Subnetz/VLAN | nur Runner + Honeypot |

Broker erreicht Runner ueber dediziertes zweites Interface (control-NIC am
svc-switch der Runner-VM entfaellt — Steuerung via Hypervisor-API + Serial/
SSH ueber sandbox-seitige Einweg-Provisionierung; Verdikt-Rueckgabe ueber
Hypervisor-Filetransfer, kein Netzpfad Sandbox→Backend).

---

## 3. Technologie-Entscheidung

**Zwei Profile, gleiche Automatisierungs-Pipeline:**

| Profil | Hypervisor | Einsatz | Begruendung |
|---|---|---|---|
| `dev-windows` | Hyper-V (Windows 10 IoT Enterprise, vorhanden) | lokale Entwicklung auf diesem Host | nativ, PowerShell-Cmdlets, Differencing-Disks |
| `prod-linux` | KVM/libvirt + QEMU | Produktions-Server | Open Source, virsh/Terraform-Provider, Linked Clones via qcow2-Backing |

**Automatisierungs-Stack (beide Profile):**

| Werkzeug | Rolle |
|---|---|
| Packer | Golden-Image-Build (Debian 12 Base + Rollen-Images), reproduzierbar |
| cloud-init | First-Boot-Provisionierung (Hostname, Netz, User, Service-Deploy) |
| Terraform (Provider: hyperv bzw. libvirt) | deklarative VM/Switch/Disk-Erzeugung |
| Ansible | Konfigurations-Drift, Service-Updates nach Erst-Provisionierung |
| PowerShell (Hyper-V-Modul) / virsh | Runner-Lifecycle (Clone, Start, Destroy) durch csve-broker |

Service-Deployment in den VMs: systemd-Units + Python-venv (kein Docker in
den VMs — sonst nur Schichten-Verdopplung). Ausnahme vm-runner: dort laeuft
weiterhin Docker (rootless) INNERHALB der VM, weil `repro.yml`-Steps
`docker build/run` referenzieren (Reporter-Kontrakt bleibt unveraendert).

---

## 3.5 Wahlmodell (zwei unabhaengige Achsen)

Die Wahl "Container oder VM" hat zwei Achsen. Nicht jede Kombination ist gueltig.

**Achse A — Stack-Deploy (wie laeuft der Gesamt-Stack):**
- `compose` — alles als Docker-Container (Ist-Zustand, Default).
- `vm` — Rollen-VMs via Packer/Terraform/Ansible (neue Variante).

**Achse B — Runner-Backend (wie wird Layer-3-Job ausgefuehrt):**
- `docker` — `dcli.containers.run(...)`, Ist-Zustand, Default.
- `vm` — ephemere Runner-VM (Linked Clone), neue Variante.

Schalter: Stack-Deploy via gewaehltem Provisionierungs-Skript
(`docker compose up` vs. `020_provision_stack.ps1`). Runner-Backend via
Env `RUNNER_BACKEND=docker|vm` in broker.py.

**Gueltige Kombinationen:**

| Stack | Runner | Status | Bemerkung |
|---|---|---|---|
| compose | docker | **Default, Ist** | unveraendert, Regressionsschutz |
| vm | vm | neu, voll | reine VM-Welt, max. Isolation |
| vm | docker | neu, zulaessig | App-VMs + Docker-in-Broker-VM (nested), Uebergang |
| compose | vm | **gesperrt** | containerisierter Broker kann Host-Hypervisor nicht treiben — out of scope |

Die gesperrte Kombination wird in broker.py beim Start hart abgewiesen
(Fehlermeldung + Exit), nicht still ignoriert.

---

## 4. Repository-Struktur (neu)

```
BugHuntyBumpy/
├── vm/
│   ├── packer/
│   │   ├── base-debian12.pkr.hcl        # Golden Base (cloud-init ready)
│   │   ├── role-ingress.pkr.hcl
│   │   ├── role-app.pkr.hcl
│   │   ├── role-data.pkr.hcl
│   │   ├── role-broker.pkr.hcl
│   │   └── role-runner.pkr.hcl          # Docker rootless + runner.py eingebrannt
│   ├── cloudinit/
│   │   ├── ingress.yml
│   │   ├── app.yml
│   │   ├── data.yml
│   │   ├── broker.yml
│   │   └── runner.yml                   # read-only-Root, tmpfs, kein Default-Routing
│   ├── terraform/
│   │   ├── main.tf                      # Switches, VMs, Disks
│   │   ├── variables.tf                 # Profil dev-windows | prod-linux
│   │   └── outputs.tf                   # IPs, SSH-Endpunkte
│   ├── ansible/
│   │   ├── inventory.tf-generated.ini
│   │   └── site.yml                     # Service-Rollen (pie, casg, relay, data)
│   └── scripts/
│       ├── 010_build_images.ps1         # Packer-Build alle Rollen
│       ├── 020_provision_stack.ps1      # terraform apply + ansible
│       ├── 030_destroy_stack.ps1
│       └── runner_spawn.ps1 / runner_spawn.sh   # vom Broker aufgerufen
└── services/csve-broker/
    ├── broker.py            # entkoppelt: Treiber-Dispatch statt harter Docker-Bindung
    ├── runner_driver.py     # Interface: spawn(job) -> verdict_json
    ├── docker_driver.py     # Ist-Docker-Logik 1:1 extrahiert (Lazy-Import docker)
    └── vm_driver.py         # neues Backend: VM statt docker run
```

---

## 5. Kernstueck: ephemere Runner-VM (Layer 3)

Ablauf pro Job (ersetzt `docker run --rm csve-runner`):

```
csve-broker
  1. BLPOP redis queue:realtime
  2. Clone:  Hyper-V  -> New-VM + Differencing-VHDX auf runner-golden.vhdx
             libvirt  -> qemu-img create -b runner-golden.qcow2 (Linked Clone)
  3. Attach: nur sandbox-switch (kein Uplink), honeypot-Subnetz
  4. Inject: repro.yml + Repo-Checkout via cloud-init NoCloud-ISO
             (seed.iso, generiert pro Job — KEIN Netz-Transfer in Sandbox)
  5. Start:  VM bootet, systemd-Unit fuehrt runner.py aus
  6. Collect: Verdikt-JSON via Hypervisor-Kanal
             (Hyper-V: KVP/Guest-Service-Interface; libvirt: virtio-serial)
  7. Destroy: Stop-VM -Force + Remove-VM + VHDX loeschen (immer, auch bei Fehler)
  8. Verdikt -> postgres, Audit -> minio (durch Broker, ausserhalb Sandbox)
```

Constraints Runner-VM (Mapping der Docker-Haertung):

| Docker-Option | VM-Aequivalent |
|---|---|
| `read_only: true` | Root-FS read-only (cloud-init), overlay-tmpfs |
| `mem_limit: 2g` / `cpus: 2.0` | VM-Konfiguration: 2 GB RAM statisch, 2 vCPU |
| `internal: true` kein Egress | Switch ohne Uplink — kein Routing-Pfad existiert |
| `pids_limit`, seccomp, cap_drop | entfaellt teilweise — Kernel-Grenze ist die VM selbst; in-VM zusaetzlich systemd `TasksMax`, kein sudo |
| Timebox 600 s | Broker-Watchdog: nach Timeout `Stop-VM -TurnOff` |

---

## 6. Phasen

### Phase 0 — Vorbereitung (0.5 Tag)
- [ ] Hyper-V-Feature pruefen/aktivieren (Windows 10 IoT Enterprise unterstuetzt es; `Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V`).
- [ ] Toolchain installieren: Packer, Terraform, Ansible (WSL2 fuer Ansible auf Windows-Host).
- [ ] Koexistenz pruefen: Docker Desktop (WSL2-Backend) + Hyper-V parallel — Konfliktcheck.
- [ ] `vm/`-Verzeichnisgeruest anlegen, `.gitignore` erweitern (`vm/output/`, `*.vhdx`, `*.qcow2`, `seed*.iso`).

### Phase 1 — Golden Images (1-2 Tage)
- [ ] `base-debian12.pkr.hcl`: Debian 12 netinst, cloud-init, SSH-Key, Hardening-Basis (unattended-upgrades aus — Determinismus).
- [ ] Rollen-Images per Packer-Build auf Base: ingress / app / data / broker / runner.
- [ ] Runner-Image: Docker rootless + runner.py + seccomp.json eingebrannt, Root-FS read-only-tauglich.
- [ ] Image-Hashes (SHA-256) in `vm/IMAGES.lock` versionieren (env_hash-Kontrakt aus Layer 4 bleibt erfuellbar).

### Phase 2 — Netz + Stack-Provisionierung (1-2 Tage)
- [ ] Terraform: 3 Switches (ext, svc, sandbox) je Profil.
- [ ] Terraform: 4 Rollen-VMs aus Golden Images, statische IPs via cloud-init.
- [ ] Ansible: Services deployen (systemd-Units fuer pie-web, casg-api, relay-worker, broker; postgres/redis/minio als native Pakete bzw. minio-Binary).
- [ ] DB-Init: `db/init/01_schema.sql` via Ansible einspielen.
- [ ] Smoke: `curl http://<vm-ingress>/api/health` gruen.

### Phase 3 — Broker-Entkopplung + VM-Driver (2-3 Tage, Kern)

**3a — Entkopplung (Pflicht zuerst, verhaltenserhaltend fuer Docker):**
- [ ] `runner_driver.py`: abstraktes Interface `spawn(report_id, repro) -> report_dict`.
- [ ] `docker_driver.py`: bestehende `run_job`/`ensure_networks`-Logik 1:1 aus broker.py extrahieren. `import docker` + `docker.from_env()` hier hinein verlagern (Lazy, erst bei Driver-Instanziierung) — kein Docker-Import mehr auf broker.py-Modul-Ebene.
- [ ] broker.py: Dispatch nach `RUNNER_BACKEND` (Default `docker`). `ensure_networks()` nur im Docker-Driver. `STACK=compose` + `RUNNER_BACKEND=vm` -> harter Abbruch mit Fehlermeldung (gesperrte Kombi §3.5).
- [ ] Regressionstest: `RUNNER_BACKEND=docker` Verhalten bit-identisch zu v-Ist (bestehende `test_broker.py` gruen, keine Anpassung der Assertions noetig).

**3b — VM-Driver (neu, opt-in):**
- [ ] `vm_driver.py`: `spawn()` mit Backends `hyperv` (PowerShell) und `libvirt` (python-libvirt). Gleiches Interface wie docker_driver.
- [ ] Seed-ISO-Generator: repro.yml + Repo-Tarball -> NoCloud-ISO pro Job.
- [ ] Verdikt-Rueckkanal: Hyper-V KVP bzw. virtio-serial, JSON-Schema unveraendert (V1/REJECTED).
- [ ] Watchdog: Timebox-Kill + garantiertes Destroy (try/finally), Orphan-Sweep beim Broker-Start.
- [ ] Unit-Tests: vm_driver gemockt (Spawn/Timeout/Destroy/Orphan/gesperrte-Kombi-Abbruch).

### Phase 4 — Airgap-Verifikation + Haertung (1 Tag)
- [ ] Egress-Test aus Runner-VM: `ping 8.8.8.8`, DNS, HTTP — alles muss scheitern.
- [ ] Lateral-Test: Runner-VM erreicht weder svc-switch noch Host (ARP/Scan leer).
- [ ] Honeypot erreichbar (wenn Profil full): Mock-OAuth antwortet.
- [ ] Ressourcen-Limits verifiziert (RAM statisch, vCPU-Cap, Timebox-Kill).
- [ ] Destroy-Garantie: Crash-Szenarien (Broker-Kill mid-job) hinterlassen keine VM-Leichen.

### Phase 5 — Doku + Abschluss (0.5 Tag)
- [ ] `BLUEPRINT_VM-Infrastruktur.md` (Pendant zu Docker-Blueprint).
- [ ] README: VM-Profil-Schnellstart-Sektion.
- [ ] CHANGELOG: Eintrag nach gruenem Gesamttest.
- [ ] Sicherheits-Checkliste (Blueprint §12) als VM-Variante uebertragen.

Gesamtaufwand: ~6-9 Arbeitstage.

---

## 7. Risiken

| Risiko | Auswirkung | Gegenmassnahme |
|---|---|---|
| Hyper-V vs. Docker-Desktop/WSL2-Konflikt auf Dev-Host | Dev blockiert | beide nutzen denselben Hypervisor-Layer — Koexistenz-Check Phase 0; Fallback: VM-Profil nur prod-linux |
| Runner-Spawn-Latenz (Boot ~10-20 s) | Realtime-Timebox-Druck | Linked Clones + minimiertes Image (kein GUI, kein initrd-Ballast); optional Warm-Pool (vorgebootete VM wartet auf Seed) |
| KVP/virtio-serial-Rueckkanal fragil | Verdikt verloren | Retry + Fallback: Verdikt-Datei auf Differencing-Disk, Broker mountet nach Stop read-only |
| Windows-10-Host: verschachtelte Virtualisierung fuer Docker-in-Runner-VM | Runner-Steps schlagen fehl | `ExposeVirtualizationExtensions` auf Runner-VM aktivieren; CPU-Support pruefen Phase 0 |
| Image-Drift (apt-Updates) bricht env_hash | Zertifikats-Kontrakt verletzt | Packer-Builds gepinnt (snapshot.debian.org), IMAGES.lock |
| Doppelte Pflege Docker + VM | Wartungslast | gemeinsame Quelle: services/-Code identisch, nur Deploy-Schicht differiert; Ansible-Rollen referenzieren dieselben Artefakte |

---

## 8. Akzeptanzkriterien

1. `010_build_images.ps1` erzeugt alle 5 Rollen-Images ohne manuelle Eingriffe.
2. `020_provision_stack.ps1` stellt kompletten Stack bereit; Health-Check gruen.
3. Submit via curl (README-Smoke-Test) durchlaeuft: Queue -> Runner-VM-Spawn -> Verdikt V1 -> postgres -> Label-Stub.
4. Runner-VM: kein Egress (Phase-4-Tests dokumentiert), automatisches Destroy in 100 % der Faelle inkl. Crash-Szenarien.
5. `RUNNER_BACKEND=docker` weiterhin voll funktionsfaehig (Regressionsfreiheit).
6. Bestehende pytest-Suite gruen.

---

## 9. Explizit ausserhalb Scope

- Firecracker/Kata-MicroVMs (bleibt Phase-2-Hook laut Blueprint §11 — dieser Plan nutzt klassische VMs).
- K8s/Helm-Migration.
- Confidential Computing (SEV-SNP/TDX).
- Produktiv-TLS/ACME (uebernommen aus Docker-Blueprint Sektion 3, unveraendert).
