# Rollen-Image broker: csve-broker (python-venv).
# Treibt ephemere Runner-VMs via Hypervisor-API (libvirt-client / virsh).
# RUNNER_BACKEND=vm setzt Ansible in der systemd-Unit-Env.
variable "profile" { type = string  default = "dev-windows" }

source "hyperv-vmcx" "broker" {
  clone_from_vmcx_path = "output/base-debian12"
  output_directory     = "output/role-broker"
  cpus = 2  memory = 2048
}
source "qemu" "broker" {
  iso_url          = "output/base-debian12/base-debian12.qcow2"
  iso_checksum     = "none"
  disk_image       = true
  use_backing_file = true
  format           = "qcow2"
  output_directory = "output/role-broker"
  ssh_username     = "bhb"  ssh_timeout = "20m"
  shutdown_command = "sudo systemctl poweroff"
}
build {
  sources = ["source.hyperv-vmcx.broker", "source.qemu.broker"]
  provisioner "shell" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y --no-install-recommends python3 python3-venv python3-pip libvirt-clients libvirt-daemon-system qemu-utils genisoimage",
      "sudo cloud-init clean --logs"
    ]
  }
}
