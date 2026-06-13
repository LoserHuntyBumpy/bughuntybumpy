<#
.SYNOPSIS  Verwaiste ephemere Runner-VMs nach Broker-Crash entfernen.
  Aufgerufen von vm_driver.sweep_orphans() beim Broker-Start (Backend hyperv).
#>
$ErrorActionPreference = "SilentlyContinue"
Get-VM -Name "bhb-runner-*" | ForEach-Object {
  Stop-VM -Name $_.Name -TurnOff -Force
  Remove-VM -Name $_.Name -Force
}
$work = if ($env:BHB_VM_WORK) { $env:BHB_VM_WORK } else { "C:\bhb\vm\work" }
Get-ChildItem -Path $work -Directory -Filter "bhb-runner-*" -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force
exit 0
