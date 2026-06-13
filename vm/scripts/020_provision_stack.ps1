<#
.SYNOPSIS  Stack-Provisionierung: terraform apply + ansible site.yml.
.DESCRIPTION
  Akzeptanzkriterium 2: stellt kompletten Stack bereit, Health-Check gruen.
  Ersetzt `docker compose up` fuer Stack-Deploy=vm (Achse A, Plan 3.5).
  1. terraform apply (Switches ext/svc/sandbox, 4 Rollen-VMs, Disks)
  2. Inventory aus terraform output generieren
  3. ansible-playbook site.yml (Service-Deploy: pie/casg/relay/data/broker)
  4. DB-Init 01_schema.sql via Ansible
  5. Smoke: curl http://<vm-ingress>/api/health
#>
[CmdletBinding()]
param(
  [ValidateSet("dev-windows","prod-linux")] [string]$Profile = "dev-windows"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Tf   = Join-Path $Root "terraform"
$Ans  = Join-Path $Root "ansible"

Push-Location $Tf
try {
  & terraform init -input=false
  & terraform apply -auto-approve -var "profile=$Profile"
  if ($LASTEXITCODE -ne 0) { throw "terraform apply fehlgeschlagen" }
  $ingressIp = (& terraform output -raw ingress_ip)
  # Inventory fuer Ansible aus TF-Output (gitignored: *.tf-generated.ini)
  & terraform output -raw ansible_inventory | Set-Content (Join-Path $Ans "inventory.tf-generated.ini")
} finally { Pop-Location }

# Ansible laeuft unter WSL2 auf dem Windows-Host (Plan Phase 0)
$inv  = (Join-Path $Ans "inventory.tf-generated.ini")
$site = (Join-Path $Ans "site.yml")
wsl ansible-playbook -i (wsl wslpath ($inv -replace '\\','/')) (wsl wslpath ($site -replace '\\','/'))
if ($LASTEXITCODE -ne 0) { throw "ansible site.yml fehlgeschlagen" }

# Smoke
Write-Host "Smoke: http://$ingressIp/api/health"
$r = Invoke-WebRequest -Uri "http://$ingressIp/api/health" -UseBasicParsing -TimeoutSec 30
if ($r.StatusCode -ne 200) { throw "Health-Check rot: $($r.StatusCode)" }
Write-Host "Stack bereit. Health gruen."
