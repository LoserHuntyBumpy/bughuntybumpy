#!/usr/bin/env bash
# Verwaiste ephemere Runner-VMs nach Broker-Crash entfernen (Backend libvirt).
# Aufgerufen von vm_driver.sweep_orphans() beim Broker-Start.
set +e
for dom in $(virsh list --all --name | grep '^bhb-runner-'); do
  virsh destroy "$dom"  >/dev/null 2>&1
  virsh undefine "$dom" --nvram >/dev/null 2>&1
done
WORK="${BHB_VM_WORK:-/var/lib/bhb/work}"
rm -rf "${WORK}"/bhb-runner-* 2>/dev/null
exit 0
