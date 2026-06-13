<#
.SYNOPSIS  Packer-Build aller 5 Rollen-Images auf Debian-12-Base.
.DESCRIPTION
  Akzeptanzkriterium 1: erzeugt alle Rollen-Images ohne manuelle Eingriffe.
  Reihenfolge: base zuerst (cloud-init-ready), dann Rollen auf Base.
  SHA-256 jeder Output-Disk in vm/IMAGES.lock (env_hash-Kontrakt Layer 4).
  Profil ueber -Profile (dev-windows = hyperv-iso, prod-linux = qemu).
#>
[CmdletBinding()]
param(
  [ValidateSet("dev-windows","prod-linux")] [string]$Profile = "dev-windows"
)
$ErrorActionPreference = "Stop"
$Root   = Split-Path -Parent $PSScriptRoot
$Packer = Join-Path $Root "packer"
$Lock   = Join-Path $Root "IMAGES.lock"

$builder = if ($Profile -eq "dev-windows") { "hyperv-iso" } else { "qemu" }
$roles = @("base-debian12","role-ingress","role-app","role-data","role-broker","role-runner")

if (-not (Get-Command packer.exe -ErrorAction SilentlyContinue)) {
  throw "packer.exe fehlt. Phase-0-Toolchain installieren."
}

"# IMAGES.lock - erzeugt $($(Get-Date).ToString('o')) Profil=$Profile" | Set-Content $Lock
foreach ($r in $roles) {
  $hcl = Join-Path $Packer "$r.pkr.hcl"
  Write-Host "packer build $r ($builder)"
  & packer.exe build -only="$builder.*" -var "profile=$Profile" $hcl
  if ($LASTEXITCODE -ne 0) { throw "packer build $r fehlgeschlagen" }
  $out = Get-ChildItem -Path (Join-Path $Root "output\$r") -Include *.vhdx,*.qcow2 -Recurse |
         Sort-Object LastWriteTime | Select-Object -Last 1
  if ($out) {
    $hash = (Get-FileHash $out.FullName -Algorithm SHA256).Hash
    "$r  $hash  $($out.Name)" | Add-Content $Lock
  }
}
Write-Host "alle Rollen-Images gebaut. Hashes in $Lock"
