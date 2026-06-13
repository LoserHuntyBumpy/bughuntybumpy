<#
.SYNOPSIS  Stack-Abbau: terraform destroy + Orphan-Runner-VMs entfernen.
#>
[CmdletBinding()]
param(
  [ValidateSet("dev-windows","prod-linux")] [string]$Profile = "dev-windows"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Tf   = Join-Path $Root "terraform"

# verwaiste ephemere Runner-VMs zuerst
Get-VM -Name "bhb-runner-*" -ErrorAction SilentlyContinue | ForEach-Object {
  Stop-VM -Name $_.Name -TurnOff -Force -ErrorAction SilentlyContinue
  Remove-VM -Name $_.Name -Force -ErrorAction SilentlyContinue
}

Push-Location $Tf
try {
  & terraform destroy -auto-approve -var "profile=$Profile"
} finally { Pop-Location }
Write-Host "Stack abgebaut."
