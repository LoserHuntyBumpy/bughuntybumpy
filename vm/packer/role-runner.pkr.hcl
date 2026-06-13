# Rollen-Image runner (Golden): Docker rootless + runner.py + seccomp.json
# eingebrannt, Root-FS read-only-tauglich. Diese Disk ist Parent fuer alle
# ephemeren Linked-Clone-Runner-VMs (Plan §5). nested virt im Gast aktiv
# (repro.yml referenziert docker build/run, Reporter-Kontrakt unveraendert).
variable "profile" { type = string  default = "dev-windows" }

source "hyperv-vmcx" "runner" {
  clone_from_vmcx_path = "output/base-debian12"
  output_directory     = "output/role-runner"
  cpus = 2  memory = 2048
}
source "qemu" "runner" {
  iso_url          = "output/base-debian12/base-debian12.qcow2"
  iso_checksum     = "none"
  disk_image       = true
  use_backing_file = true
  format           = "qcow2"
  output_directory = "output/role-runner"
  ssh_username     = "bhb"  ssh_timeout = "20m"
  shutdown_command = "sudo systemctl poweroff"
}
build {
  sources = ["source.hyperv-vmcx.runner", "source.qemu.runner"]
  provisioner "file" {
    source      = "../../services/csve-runner/runner.py"
    destination = "/tmp/runner.py"
  }
  provisioner "file" {
    source      = "../../services/csve-runner/seccomp.json"
    destination = "/tmp/seccomp.json"
  }
  provisioner "shell" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y --no-install-recommends docker.io uidmap python3 python3-venv",
      "sudo install -m 0755 /tmp/runner.py /opt/runner.py",
      "sudo install -m 0644 /tmp/seccomp.json /opt/seccomp.json",
      # systemd-Unit liest /repro (Seed-ISO via cloud-init) und schreibt Verdikt auf Results-Disk
      "sudo install -m 0644 /tmp/cloudinit-runner.service /etc/systemd/system/bhb-runner.service || true",
      "sudo systemctl enable bhb-runner.service || true",
      "sudo cloud-init clean --logs"
    ]
  }
}
