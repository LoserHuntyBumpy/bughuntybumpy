# Rollen-Image app: pie-web, casg-api, relay-worker (systemd + python-venv).
# Code aus services/ wird via Ansible deployt; Image traegt nur Runtime.
variable "profile" { type = string  default = "dev-windows" }

source "hyperv-vmcx" "app" {
  clone_from_vmcx_path = "output/base-debian12"
  output_directory     = "output/role-app"
  cpus = 2  memory = 4096
}
source "qemu" "app" {
  iso_url          = "output/base-debian12/base-debian12.qcow2"
  iso_checksum     = "none"
  disk_image       = true
  use_backing_file = true
  format           = "qcow2"
  output_directory = "output/role-app"
  ssh_username     = "bhb"  ssh_timeout = "20m"
  shutdown_command = "sudo systemctl poweroff"
}
build {
  sources = ["source.hyperv-vmcx.app", "source.qemu.app"]
  provisioner "shell" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y --no-install-recommends python3 python3-venv python3-pip git",
      "sudo cloud-init clean --logs"
    ]
  }
}
