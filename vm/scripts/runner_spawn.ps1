<#
.SYNOPSIS
  Ephemere Hyper-V Runner-VM: Clone -> Seed -> Start -> Collect -> Destroy.
  Aufgerufen von services/csve-broker/vm_driver.py (Backend hyperv).

.DESCRIPTION
  Verhaltens-Aequivalent zu `docker run --rm csve-runner`:
    - Differencing-VHDX auf runner-golden.vhdx (Linked Clone)
    - nur sandbox-switch (kein Uplink, physisch kein Egress)
    - 2 GB RAM statisch, 2 vCPU (Mapping mem_limit/cpus)
    - NoCloud-Seed-ISO injiziert repro.yml (kein Netz-Transfer)
    - Verdikt-Rueckkanal: Results-VHDX, nach Stop read-only gemountet
    - Timebox-Kill (Stop-VM -TurnOff) + garantiertes Destroy (finally)

  Exit 0 = Lifecycle ok (Verdikt-Datei geschrieben oder begruendet leer).
  Exit !=0 = Spawn-Fehler; vm_driver wertet als REJECTED.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string]$JobId,
  [Parameter(Mandatory)] [string]$SeedIso,      # Seed-Verzeichnis (enthaelt repro.yml/meta-data)
  [Parameter(Mandatory)] [string]$VerdictOut,   # Zielpfad verdict.json (host-seitig)
  [int]$TimeboxSec = 600
)

$ErrorActionPreference = "Stop"
$VmName       = "bhb-runner-$JobId"
$GoldenVhdx   = $env:RUNNER_GOLDEN_VHDX ; if (-not $GoldenVhdx) { $GoldenVhdx = "C:\bhb\vm\images\runner-golden.vhdx" }
$SandboxSwitch= $env:BHB_SANDBOX_SWITCH ; if (-not $SandboxSwitch) { $SandboxSwitch = "bhb-sandbox-switch" }
$WorkRoot     = $env:BHB_VM_WORK ;        if (-not $WorkRoot) { $WorkRoot = "C:\bhb\vm\work" }
$VmDir        = Join-Path $WorkRoot $VmName
$DiffVhdx     = Join-Path $VmDir "$VmName.vhdx"
$ResultsVhdx  = Join-Path $VmDir "$VmName-results.vhdx"
$SeedImg      = Join-Path $VmDir "seed.iso"

function Build-SeedIso {
  param([string]$SrcDir, [string]$OutIso)
  # oscdimg (Windows ADK) erzeugt NoCloud-Label CIDATA. Kein Netzpfad.
  $oscdimg = (Get-Command oscdimg.exe -ErrorAction SilentlyContinue)
  if (-not $oscdimg) { throw "oscdimg.exe fehlt (Windows ADK). NoCloud-Seed nicht baubar." }
  & oscdimg.exe -lCIDATA -m -o "$SrcDir" "$OutIso" | Out-Null
}

New-Item -ItemType Directory -Force -Path $VmDir | Out-Null

try {
  # 1. Seed-ISO host-seitig bauen (repro.yml liegt in $SeedIso-Verzeichnis)
  Build-SeedIso -SrcDir $SeedIso -OutIso $SeedImg

  # 2. Linked Clone (Differencing-Disk auf Golden)
  New-VHD -Path $DiffVhdx -ParentPath $GoldenVhdx -Differencing | Out-Null
  # Results-Disk fuer Verdikt-Rueckgabe (guest schreibt verdict.json hierauf)
  New-VHD -Path $ResultsVhdx -SizeBytes 64MB -Dynamic | Out-Null

  # 3. VM erzeugen, nur sandbox-switch (kein Uplink)
  New-VM -Name $VmName -MemoryStartupBytes 2GB -Generation 2 `
         -VHDPath $DiffVhdx -SwitchName $SandboxSwitch | Out-Null
  Set-VM -Name $VmName -StaticMemory -ProcessorCount 2 `
         -AutomaticCheckpointsEnabled $false
  Set-VMMemory -VMName $VmName -StartupBytes 2GB -MaximumBytes 2GB -MinimumBytes 2GB
  # nested virt fuer Docker-in-Runner-VM (repro.yml docker build/run)
  Set-VMProcessor -VMName $VmName -ExposeVirtualizationExtensions $true
  Add-VMDvdDrive -VMName $VmName -Path $SeedImg
  Add-VMHardDiskDrive -VMName $VmName -Path $ResultsVhdx

  # 4. Start + Timebox-Watchdog
  Start-VM -Name $VmName
  $deadline = (Get-Date).AddSeconds($TimeboxSec)
  while ((Get-VM -Name $VmName).State -eq 'Running' -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
  }
  if ((Get-VM -Name $VmName).State -eq 'Running') {
    Stop-VM -Name $VmName -TurnOff -Force   # Timebox ueberschritten
  }

  # 5. Verdikt einsammeln: Results-VHDX read-only mounten, verdict.json lesen
  $mount = Mount-VHD -Path $ResultsVhdx -ReadOnly -PassThru | Get-Disk | `
           Get-Partition | Get-Volume | Where-Object DriveLetter
  try {
    $src = Join-Path ($mount.DriveLetter + ":\") "verdict.json"
    if (Test-Path $src) { Copy-Item $src $VerdictOut -Force }
  } finally {
    Dismount-VHD -Path $ResultsVhdx
  }
}
finally {
  # 6. Garantiertes Destroy (auch bei Fehler/Timeout)
  if (Get-VM -Name $VmName -ErrorAction SilentlyContinue) {
    Stop-VM -Name $VmName -TurnOff -Force -ErrorAction SilentlyContinue
    Remove-VM -Name $VmName -Force -ErrorAction SilentlyContinue
  }
  Remove-Item -Recurse -Force $VmDir -ErrorAction SilentlyContinue
}
exit 0
