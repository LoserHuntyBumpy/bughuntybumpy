# BugHuntyBumpy - Linux-Deploy

Deploy-Skripte fuer Compose-Stack auf Linux-Server (Docker CE + Compose v2).

## Reihenfolge

```bash
sudo deploy/deploy.sh          # alles: prereqs + bootstrap + deploy
```

Oder einzeln:

```bash
sudo deploy/00_prereqs.sh      # Docker/Compose/openssl/iptables pruefen
     deploy/01_bootstrap.sh    # .env erzeugen, starke Random-Secrets, chmod 600
sudo deploy/02_deploy.sh       # Build Kern + Runner-Image, up -d, Health, Airgap
```

## Skripte

| Skript | Zweck |
|---|---|
| `00_prereqs.sh` | Voraussetzungen pruefen/installieren (Root). |
| `01_bootstrap.sh` | `.env` aus `.env.example`, Platzhalter `change-me-strong` -> `openssl rand`. Stoppt hart bei Rest-Platzhaltern. |
| `02_deploy.sh` | `docker compose build`, Runner-Image (build-only), `up -d` Kern, Health-Wait, `host-firewall.sh`. |
| `03_teardown.sh` | Stack stoppen. `--purge` loescht Volumes (Datenverlust). |
| `deploy.sh` | Wrapper 00->01->02. |
| `bhb.service` | systemd-Unit fuer Boot-Start. Pfad anpassen, dann `enable --now`. |

## Ports

| Port | Dienst |
|---|---|
| 6080 | Ingress (traefik web) -> Formular + `/api`. |
| 6088 | traefik-Dashboard. **Vor Internet-Exponierung schliessen oder Auth** (Audit S5). |

## Boot-Start (systemd)

```bash
sudo cp deploy/bhb.service /etc/systemd/system/bhb.service
sudo sed -i 's|/opt/BugHuntyBumpy|'"$(pwd)"'|g' /etc/systemd/system/bhb.service
sudo systemctl daemon-reload
sudo systemctl enable --now bhb
```

## Hinweise

- Skripte sind idempotent; erneuter Lauf ueberschreibt keine echten Secrets.
- `host-firewall.sh` braucht Root und das Sandbox-Netz (von `compose up` erzeugt).
  Persistenz des iptables-Blocks ueber Reboot: `iptables-save` / `netfilter-persistent`.
- Firewall am Host zusaetzlich: nur 6080 oeffentlich, 6088 nur lokal/VPN.
