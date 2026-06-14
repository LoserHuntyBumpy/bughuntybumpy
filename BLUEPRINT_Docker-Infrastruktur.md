# BugHuntyBumpy - Docker-Infrastruktur-Blueprint

**Version:** 1.0
**Quelle:** Konzept4_Master-Fusion.md (v2.0)
**Ziel:** Vollstaendig lauffaehige Container-Infra, 5-Layer-Architektur, Sandbox-Airgap.
**Scope:** MVP-tauglich (Phase 1) + Erweiterungs-Hooks (Phase 2/3 markiert).

---

## 1. Topologie-Uebersicht

5 Layer aus Konzept → Container-Services. Strikte Netz-Trennung erzwingt Layer-3-Airgap (§5.5 Konzept).

```
                       INTERNET
                          │
                    ┌─────┴─────┐
                    │  traefik  │  (Reverse-Proxy, TLS, einziger Ingress)
                    └─────┬─────┘
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   ┌─────────┐      ┌──────────┐      ┌──────────┐
   │ pie-web │      │ casg-web │      │ relay-api│   net: frontend
   │ (L1 UI) │      │ (L2 UI)  │      │ (L5 API) │
   └────┬────┘      └────┬─────┘      └────┬─────┘
        │                │                 │
  ══════╪════════════════╪═════════════════╪══════  net: backend (internal)
        ▼                │                 │
   ┌─────────┐      ┌────▼─────┐      ┌────▼─────┐
   │ pie-    │      │ casg-api │      │ relay-   │
   │ scanner │      │ (Gateway)│      │ worker   │
   │ (L1)    │      └────┬─────┘      │ (GitHub) │
   └─────────┘           │            └──────────┘
                         ▼
                    ┌─────────┐
                    │ csve-   │   Job-Dispatch (kein Datenpfad in Sandbox)
                    │ broker  │   (L3 Orchestrator)
                    └────┬────┘
                         │ (control only)
  ═══════════════════════╪══════════════════════════  net: sandbox (internal:true, NO egress)
                         ▼
                    ┌─────────┐      ┌──────────────┐
                    │ csve-   │◄────►│ honeypot-net │  Mock-OAuth/DB/SMTP/S3/C2
                    │ runner  │      │ (L3 §5.3)    │
                    │ (DinD/  │      └──────────────┘
                    │ rootless)│
                    └─────────┘

  Daten-Backbone (net: backend):  postgres │ redis │ minio │ cert-signer
```

**Netz-Regeln:**
- `frontend`: bridge, Internet-exponiert nur ueber traefik.
- `backend`: `internal: true`, kein Internet, traegt App-zu-DB-Verkehr.
- `sandbox`: `internal: true`, zusaetzlich Egress hart geblockt. CSVE-Runner sieht nur `honeypot-net`. Kein DNS nach aussen.
- `honeypot-net`: `internal: true`, isoliert. Nur Runner + Mock-Services.

---

## 2. Service-Inventar

| Service | Layer | Image-Basis | Netz | Rolle |
|---|---|---|---|---|
| `traefik` | - | traefik:v3.1 | frontend | TLS-Termination, Routing, einziger Ingress |
| `pie-web` | L1 | node:20-alpine (Vue/React build → nginx) | frontend, backend | Formular-UI (`bughunty.yml` gerendert) |
| `pie-scanner` | L1 | python:3.12-slim + semgrep/tree-sitter/osv | backend | Repo-Analyse, deterministisch, kein Internet zur Laufzeit |
| `casg-web` | L2 | nginx static | frontend, backend | Submission-UI, Reframe-Editor |
| `casg-api` | L2 | python:3.12-slim (FastAPI) | frontend, backend | Gate-Logik, Respekt-Gate, Repro-Intake |
| `csve-broker` | L3 | golang:1.23 (compiled) | backend, sandbox | Job-Queue-Consumer, provisioniert Runner |
| `csve-runner` | L3 | docker:27-dind-rootless | sandbox, honeypot-net | Closed-Shell-Ausfuehrung `repro.sh`/`repro.yml` |
| `honeypot-mock` | L3 | python:3.12-slim | honeypot-net | Mock OAuth/DB/SMTP/S3/C2-Sim (§5.3) |
| `cert-signer` | L4 | python:3.12-slim (Ed25519) | backend | Validation-Certificate-Signatur |
| `relay-api` | L5 | python:3.12-slim (FastAPI) | frontend, backend | Output-Paket, Ranking, Dedup |
| `relay-worker` | L5 | python:3.12-slim | backend | GitHub-Bot (Label, Badge-Kommentar) |
| `postgres` | DB | postgres:16-alpine | backend | Reports, Verdikte, Reputation |
| `redis` | Queue | redis:7-alpine | backend | Job-Queue (Echtzeit/Overnight), Rate-Limit |
| `minio` | Storage | minio/minio | backend | Audit-Logs, asciinema, Repro-Repos, Build-Cache |

---

## 3. docker-compose.yml (Produktions-Grundgeruest)

```yaml
name: bughuntybumpy

x-logging: &default-logging
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true
  sandbox:
    driver: bridge
    internal: true
  honeypot-net:
    driver: bridge
    internal: true

volumes:
  pg-data:
  minio-data:
  redis-data:
  cert-keys:
  buildcache:

services:

  # ---------- Ingress ----------
  traefik:
    image: traefik:v3.1
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.le.acme.email=eisenberger@tutanota.com"
      - "--certificatesresolvers.le.acme.storage=/letsencrypt/acme.json"
      - "--certificatesresolvers.le.acme.tlschallenge=true"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "./letsencrypt:/letsencrypt"
    networks: [frontend]
    restart: unless-stopped
    logging: *default-logging

  # ---------- Layer 1: PIE ----------
  pie-web:
    build: ./services/pie-web
    networks: [frontend, backend]
    depends_on: [pie-scanner]
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.pie.rule=Host(`pie.bhb.local`)"
      - "traefik.http.routers.pie.entrypoints=websecure"
      - "traefik.http.routers.pie.tls.certresolver=le"
      - "traefik.http.services.pie.loadbalancer.server.port=80"
    restart: unless-stopped
    logging: *default-logging

  pie-scanner:
    build: ./services/pie-scanner
    networks: [backend]
    environment:
      - DATABASE_URL=postgresql://bhb:${PG_PASSWORD}@postgres:5432/bhb
      - OSV_OFFLINE_DB=/data/osv
    volumes:
      - "./data/repos:/repos:ro"        # zu scannende Repos read-only
      - "./data/osv:/data/osv:ro"       # Offline-OSV-DB
    depends_on: [postgres]
    # kein Internet: nur backend-net. OSV offline.
    restart: unless-stopped
    logging: *default-logging

  # ---------- Layer 2: CASG ----------
  casg-web:
    build: ./services/casg-web
    networks: [frontend, backend]
    depends_on: [casg-api]
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.casg.rule=Host(`submit.bhb.local`)"
      - "traefik.http.routers.casg.entrypoints=websecure"
      - "traefik.http.routers.casg.tls.certresolver=le"
      - "traefik.http.services.casg.loadbalancer.server.port=80"
    restart: unless-stopped
    logging: *default-logging

  casg-api:
    build: ./services/casg-api
    networks: [frontend, backend]
    environment:
      - DATABASE_URL=postgresql://bhb:${PG_PASSWORD}@postgres:5432/bhb
      - REDIS_URL=redis://redis:6379/0
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
    depends_on: [postgres, redis, minio]
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.casgapi.rule=Host(`submit.bhb.local`) && PathPrefix(`/api`)"
      - "traefik.http.routers.casgapi.entrypoints=websecure"
      - "traefik.http.routers.casgapi.tls.certresolver=le"
      - "traefik.http.services.casgapi.loadbalancer.server.port=8000"
    restart: unless-stopped
    logging: *default-logging

  # ---------- Layer 3: CSVE ----------
  csve-broker:
    build: ./services/csve-broker
    networks: [backend, sandbox]
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql://bhb:${PG_PASSWORD}@postgres:5432/bhb
      - RUNNER_IMAGE=bhb/csve-runner:latest
      - REALTIME_TIMEBOX_SEC=600
      - OVERNIGHT_TIMEBOX_SEC=14400
    volumes:
      - "buildcache:/buildcache"
    depends_on: [redis, postgres]
    restart: unless-stopped
    logging: *default-logging

  csve-runner:
    build: ./services/csve-runner
    image: bhb/csve-runner:latest
    networks: [sandbox, honeypot-net]
    # Hostile-Reporter-by-Design: maximale Restriktion
    privileged: false
    read_only: true
    security_opt:
      - "no-new-privileges:true"
      - "seccomp=./services/csve-runner/seccomp.json"
    cap_drop: ["ALL"]
    pids_limit: 256
    mem_limit: 2g
    cpus: 2.0
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=512m
    environment:
      - NO_EGRESS=1
      - HONEYPOT_HOST=honeypot-mock
    # NICHT direkt gestartet - csve-broker provisioniert ephemere Instanzen.
    # Hier nur Image-Build + Default-Constraints definiert.
    profiles: ["build-only"]
    restart: "no"
    logging: *default-logging

  honeypot-mock:
    build: ./services/honeypot-mock
    networks: [honeypot-net]
    environment:
      - SERVICES=oauth,postgres-mock,smtp-trap,s3-mock,c2-sim,metadata
    read_only: true
    cap_drop: ["ALL"]
    restart: unless-stopped
    logging: *default-logging

  # ---------- Layer 4: Trust ----------
  cert-signer:
    build: ./services/cert-signer
    networks: [backend]
    environment:
      - SIGNING_KEY_PATH=/keys/ed25519.key
      - DATABASE_URL=postgresql://bhb:${PG_PASSWORD}@postgres:5432/bhb
    volumes:
      - "cert-keys:/keys"
    depends_on: [postgres]
    restart: unless-stopped
    logging: *default-logging

  # ---------- Layer 5: Maintainer Relay ----------
  relay-api:
    build: ./services/relay-api
    networks: [frontend, backend]
    environment:
      - DATABASE_URL=postgresql://bhb:${PG_PASSWORD}@postgres:5432/bhb
      - REDIS_URL=redis://redis:6379/0
    depends_on: [postgres, redis]
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.relay.rule=Host(`relay.bhb.local`)"
      - "traefik.http.routers.relay.entrypoints=websecure"
      - "traefik.http.routers.relay.tls.certresolver=le"
      - "traefik.http.services.relay.loadbalancer.server.port=8000"
    restart: unless-stopped
    logging: *default-logging

  relay-worker:
    build: ./services/relay-worker
    networks: [backend]
    environment:
      - DATABASE_URL=postgresql://bhb:${PG_PASSWORD}@postgres:5432/bhb
      - REDIS_URL=redis://redis:6379/0
      - GITHUB_APP_ID=${GITHUB_APP_ID}
      - GITHUB_APP_KEY_PATH=/keys/github-app.pem
    volumes:
      - "./secrets/github-app.pem:/keys/github-app.pem:ro"
    depends_on: [postgres, redis]
    restart: unless-stopped
    logging: *default-logging

  # ---------- Daten-Backbone ----------
  postgres:
    image: postgres:16-alpine
    networks: [backend]
    environment:
      - POSTGRES_USER=bhb
      - POSTGRES_PASSWORD=${PG_PASSWORD}
      - POSTGRES_DB=bhb
    volumes:
      - "pg-data:/var/lib/postgresql/data"
      - "./db/init:/docker-entrypoint-initdb.d:ro"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bhb"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    logging: *default-logging

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    networks: [backend]
    volumes:
      - "redis-data:/data"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped
    logging: *default-logging

  minio:
    image: minio/minio
    command: ["server", "/data", "--console-address", ":9001"]
    networks: [backend]
    environment:
      - MINIO_ROOT_USER=${MINIO_ACCESS_KEY}
      - MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY}
    volumes:
      - "minio-data:/data"
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 15s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    logging: *default-logging
```

---

## 4. .env (Secrets-Vorlage)

```dotenv
# .env  - NICHT committen. In .gitignore.
PG_PASSWORD=change-me-strong
MINIO_ACCESS_KEY=bhbminio
MINIO_SECRET_KEY=change-me-strong
GITHUB_APP_ID=000000
```

`secrets/github-app.pem` separat ablegen, read-only gemountet. `.gitignore`: `.env`, `secrets/`, `letsencrypt/`, `data/`.

---

## 5. Kritischer Service: csve-runner (Layer 3, Closed-Shell)

Herzstueck. Determinismus + Airgap. MVP nutzt rootless DinD statt Firecracker (§9 Phase 1 Konzept).

### 5.1 Dockerfile

```dockerfile
# services/csve-runner/Dockerfile
FROM docker:27-dind-rootless

USER root
RUN apk add --no-cache python3 py3-yaml bash git
COPY runner.py /opt/runner.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

# Rootless: kein root-Daemon-Zugriff von innen
USER rootless
ENTRYPOINT ["/opt/entrypoint.sh"]
```

### 5.2 runner.py (Replay-Kern, MVP: Exit-Code-Assertion)

```python
#!/usr/bin/env python3
"""CSVE Closed-Shell Runner - deterministisch, KEINE KI.
Input: repro.yml + Ziel-Repo-Checkout (commit-pinned).
Output: Verdikt-JSON (V1/V2/V3) → stdout, Audit-Log → /audit.
"""
import json, subprocess, sys, time, hashlib, os

REALTIME_TIMEBOX = int(os.getenv("STEP_TIMEOUT_SEC", "120"))

def run_step(cmd, expect_exit=None, expect_substr=None):
    t0 = time.time()
    proc = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        timeout=REALTIME_TIMEBOX,
    )
    out = (proc.stdout + proc.stderr)[:50000]
    ok = True
    if expect_exit is not None and proc.returncode != expect_exit:
        ok = False
    if expect_substr is not None and expect_substr not in out:
        ok = False
    return {
        "cmd": cmd, "exit": proc.returncode,
        "duration_ms": int((time.time() - t0) * 1000),
        "output_hash": hashlib.sha256(out.encode()).hexdigest(),
        "matched": ok, "output_tail": out[-2000:],
    }

def main(repro_path):
    with open(repro_path) as f:
        import yaml
        spec = yaml.safe_load(f)

    results, verified = [], True
    for step in spec.get("steps", []):
        r = run_step(
            step["run"],
            expect_exit=step.get("expect_exit"),
            expect_substr=step.get("expect_output"),
        )
        results.append(r)
        if not r["matched"]:
            verified = False
            break  # deterministisch: erster Mismatch beendet

    verdict = "V1" if verified else "REJECTED"
    report = {
        "verdict": verdict,
        "verdict_class": "deterministic" if verified else "none",
        "steps": results,
        "repro_hash": hashlib.sha256(open(repro_path, "rb").read()).hexdigest(),
    }
    json.dump(report, sys.stdout)
    print()
    return 0 if verified else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
```

### 5.3 repro.yml (Reporter-Eingabe, vgl. §4.4 Konzept)

```yaml
# Reporter liefert. Maschinenlesbar. Kein Freitext.
target_repo: https://gitea.bhb.local/reporter/minimal-repro.git
commit: a1b2c3d
steps:
  - name: "build target"
    run: "docker build -t target ."
    expect_exit: 0
  - name: "trigger SQLi"
    run: |
      docker run --rm --network none target \
        sh -c "curl -s -X POST http://localhost:5000/search -d \"q=' OR '1'='1\""
    expect_output: "1247 rows"
    expect_exit: 0
```

### 5.4 Egress-Block (Pflicht, Hostile-Reporter)

`sandbox` + `honeypot-net` sind `internal: true` → kein NAT, kein Internet. Zusaetzlich Host-Firewall-Regel als zweite Linie:

```bash
# host-firewall.sh - beim Deploy ausfuehren. iptables-Hard-Block fuer sandbox-subnet.
SANDBOX_SUBNET=$(docker network inspect bughuntybumpy_sandbox \
  -f '{{ (index .IPAM.Config 0).Subnet }}')
iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" ! -d "$SANDBOX_SUBNET" -j DROP
iptables -I DOCKER-USER -s "$SANDBOX_SUBNET" -o eth0 -j DROP
```

---

## 6. Datenbank-Init (db/init/01_schema.sql)

```sql
CREATE TABLE projects (
    id          TEXT PRIMARY KEY,        -- org/repo
    bughunty_yml JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  TEXT REFERENCES projects(id),
    commit_hash TEXT NOT NULL,
    repro_class CHAR(1) CHECK (repro_class IN ('A','B','C')),
    tone_tag    TEXT,                    -- neutral|urgent|emotional
    repro_hash  TEXT,                    -- Dedup (TLSH/ssdeep)
    status      TEXT DEFAULT 'submitted',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE verdicts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id   UUID REFERENCES reports(id),
    verdict     TEXT CHECK (verdict IN ('V1','V2','V3','REJECTED')),
    severity    TEXT,                    -- P0..P4
    audit_ref   TEXT,                    -- minio-Pfad
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE certificates (
    id          TEXT PRIMARY KEY,        -- BHB-2024-001
    verdict_id  UUID REFERENCES verdicts(id),
    commit_hash TEXT,
    env_hash    TEXT,
    signature   TEXT NOT NULL,           -- Ed25519
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE reporters (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    handle      TEXT UNIQUE,
    trust_level INT DEFAULT 0,           -- Express-Modus ab Schwelle
    v1_count    INT DEFAULT 0
);
```

---

## 7. Job-Flow (Echtzeit vs. Overnight, §5.6)

```
casg-api  ──push──►  redis: queue:realtime  (Timebox 10min)
                     redis: queue:overnight (Timebox 4h, Oversized-Build)
                          │
csve-broker  ──BLPOP──────┘
   │ 1. resolve repro.yml + commit
   │ 2. check buildcache (minio/nix-store-pfad)
   │ 3. docker run --rm ephemere csve-runner (sandbox+honeypot-net)
   │ 4. capture verdict-JSON + audit-log → minio
   │ 5. verdict → postgres
   │ 6. wenn V1 → cert-signer (Ed25519) → certificates
   │ 7. notify relay-api
   ▼
relay-worker  ──GitHub-App──►  Label bhb-verified / bhb-stochastic + Badge-Kommentar
```

Rate-Limit (redis): `INCR rl:reporter:<id>` mit TTL. Teure Sandbox erst nach billiger Plausibilitaet (casg-api Versions-/Dup-Check).

---

## 8. Verzeichnis-Layout

```
BugHuntyBumpy/
├── docker-compose.yml
├── docker-compose.override.yml      # lokale Dev-Overrides
├── .env                             # gitignored
├── host-firewall.sh
├── db/init/01_schema.sql
├── secrets/github-app.pem           # gitignored
├── data/                            # repos, osv-db (gitignored)
├── letsencrypt/                     # gitignored
└── services/
    ├── pie-web/{Dockerfile,...}
    ├── pie-scanner/{Dockerfile,scan.py,requirements.txt}
    ├── casg-web/{Dockerfile,nginx.conf}
    ├── casg-api/{Dockerfile,app.py,requirements.txt}
    ├── csve-broker/{Dockerfile,main.go}
    ├── csve-runner/{Dockerfile,runner.py,entrypoint.sh,seccomp.json}
    ├── honeypot-mock/{Dockerfile,mock.py}
    ├── cert-signer/{Dockerfile,sign.py}
    ├── relay-api/{Dockerfile,app.py}
    └── relay-worker/{Dockerfile,bot.py}
```

---

## 9. Inbetriebnahme

```bash
# 1. Secrets setzen
cp .env.example .env && $EDITOR .env

# 2. Signing-Key fuer Zertifikate erzeugen (Ed25519, einmalig)
docker compose run --rm cert-signer python -c \
  "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; \
   k=Ed25519PrivateKey.generate(); import sys; \
   open('/keys/ed25519.key','wb').write(k.private_bytes_raw())"

# 3. Runner-Image vorbauen
docker compose build csve-runner

# 4. Backbone zuerst, dann App-Layer
docker compose up -d postgres redis minio
docker compose up -d

# 5. Host-Firewall (Sandbox-Airgap zweite Linie)
sudo ./host-firewall.sh

# 6. Smoke-Test
curl -fsS https://submit.bhb.local/api/health
```

Hosts-Eintraege lokal: `pie.bhb.local submit.bhb.local relay.bhb.local → 127.0.0.1`.

---

## 10. MVP-Reduktion (Konzept §9 Phase 1)

Fuer Erst-Demo abschaltbar (compose-Profiles oder weglassen):
- `cert-signer`, `honeypot-mock`, `pie-scanner` (PIE manuell → `bughunty.yml` von Hand).
- `csve-runner` bleibt = Kern. Nur Exit-Code-Assertion. Kein eBPF, kein Nix, kein Firecracker.
- `relay-worker` = GitHub-Bot-Badge.

Minimal-Set MVP: `traefik`, `casg-api`, `casg-web`, `csve-broker`, `csve-runner`, `postgres`, `redis`, `relay-worker`.
- **TLS/ACME auskommentiert fuer lokalen Smoke-Test.** Phase-1-MVP: PathPrefix-Routing auf :80. Produktiv: Blueprint-Sektion 3 unkommentieren.

## 11. Phase-2/3-Hooks (markiert, nicht im Grundgeruest)

- **Firecracker/Kata**: `csve-runner` → microVM-Runner. Broker tauscht `docker run` gegen `firecracker`-Spawn. Sandbox-Netz bleibt.
- **eBPF/Falco-Observation**: Sidecar im Runner-Pod (K8s), Syscall-Capture → Assertion-Engine (Rego/OPA).
- **Confidential Computing**: V1-Security-Laeufe auf SEV-SNP/TDX-Bare-Metal-Node-Pool, ausserhalb compose → K8s + Node-Selector.
- **Build-Cache-Service**: minio `buildcache` → Nix-Store-Remote (`nix copy`).
- **K8s-Migration**: compose → Helm-Chart. Sandbox-Netz → NetworkPolicy `egress: deny-all`.

---

## 12. Sicherheits-Checkliste (vor Produktiv)

- [ ] `sandbox` + `honeypot-net` verifiziert `internal: true`, kein Egress (`docker run --network sandbox alpine ping 8.8.8.8` muss scheitern).
- [ ] csve-runner: `read_only`, `cap_drop ALL`, `no-new-privileges`, seccomp aktiv, pids/mem/cpu-Limits gesetzt.
- [ ] Keine echten Secrets in Sandbox. Honeypot liefert Fake-Credentials.
- [ ] Host-Firewall-Regel `DOCKER-USER` aktiv und persistiert (iptables-save / nftables).
- [ ] `.env`, `secrets/`, `letsencrypt/`, `data/` in `.gitignore`.
- [ ] traefik einziger Port-Publisher. Backbone-Services (`postgres`/`redis`/`minio`) NICHT geportforwarded.
- [ ] Runner ephemere (`--rm`), keine Disk-Persistence, HIDS terminiert Ausreisser.
