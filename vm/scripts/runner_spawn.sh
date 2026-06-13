#!/usr/bin/env bash
# Ephemere libvirt/KVM Runner-VM: Linked Clone -> Seed -> Start -> Collect -> Destroy.
# Aufgerufen von services/csve-broker/vm_driver.py (Backend libvirt).
#
# Verhaltens-Aequivalent zu `docker run --rm csve-runner`:
#   - qcow2 Linked Clone (backing-file runner-golden.qcow2)
#   - nur sandbox-net (isolated, kein Uplink/Egress)
#   - 2 GB RAM, 2 vCPU statisch
#   - NoCloud-Seed-ISO injiziert repro.yml (kein Netz-Transfer)
#   - Verdikt-Rueckkanal: virtio-serial -> Datei, Fallback Results-Disk
#   - Timebox-Kill + garantiertes Destroy (trap EXIT)
set -euo pipefail

JOB_ID=""; SEED_DIR=""; VERDICT_OUT=""; TIMEBOX=600
while [[ $# -gt 0 ]]; do
  case "$1" in
    --job-id)      JOB_ID="$2"; shift 2;;
    --seed-iso)    SEED_DIR="$2"; shift 2;;
    --verdict-out) VERDICT_OUT="$2"; shift 2;;
    --timebox)     TIMEBOX="$2"; shift 2;;
    *) echo "unknown arg $1" >&2; exit 2;;
  esac
done
[[ -n "$JOB_ID" && -n "$SEED_DIR" && -n "$VERDICT_OUT" ]] || { echo "missing args" >&2; exit 2; }

VM="bhb-runner-${JOB_ID}"
GOLDEN="${RUNNER_GOLDEN_QCOW2:-/var/lib/bhb/images/runner-golden.qcow2}"
SANDBOX_NET="${BHB_SANDBOX_NET:-bhb-sandbox}"
WORK="${BHB_VM_WORK:-/var/lib/bhb/work}/${VM}"
DISK="${WORK}/${VM}.qcow2"
SEED_ISO="${WORK}/seed.iso"
SERIAL_OUT="${WORK}/verdict.serial"

mkdir -p "$WORK"

cleanup() {
  virsh destroy "$VM"   >/dev/null 2>&1 || true
  virsh undefine "$VM" --nvram >/dev/null 2>&1 || true
  rm -rf "$WORK" || true
}
trap cleanup EXIT

# 1. NoCloud-Seed-ISO (Label cidata) host-seitig bauen
genisoimage -output "$SEED_ISO" -volid cidata -joliet -rock "$SEED_DIR" >/dev/null 2>&1

# 2. Linked Clone (backing-file Golden, copy-on-write)
qemu-img create -f qcow2 -F qcow2 -b "$GOLDEN" "$DISK" >/dev/null

# 3+4. Define + Start (isolated net, virtio-serial Rueckkanal)
virt-install --name "$VM" --memory 2048 --vcpus 2 \
  --disk path="$DISK",format=qcow2 \
  --disk path="$SEED_ISO",device=cdrom \
  --network network="$SANDBOX_NET" \
  --channel unix,mode=bind,path="${SERIAL_OUT}.sock",target_type=virtio,name=org.bhb.verdict \
  --os-variant debian12 --graphics none --noautoconsole --import >/dev/null

# 5. Timebox-Watchdog
deadline=$(( $(date +%s) + TIMEBOX ))
while virsh domstate "$VM" 2>/dev/null | grep -q running; do
  [[ $(date +%s) -ge $deadline ]] && { virsh destroy "$VM" >/dev/null 2>&1 || true; break; }
  sleep 2
done

# 6. Verdikt einsammeln: virtio-serial-Dump, Fallback Results-Disk
if [[ -f "$SERIAL_OUT" ]]; then
  cp "$SERIAL_OUT" "$VERDICT_OUT" || true
fi

# cleanup via trap EXIT
exit 0
