# Rollen-Image ingress: nginx/traefik (TLS-Terminierung, Routing).
# Baut auf base-debian12-Output (Parent-Disk). Netze: ext + svc.
variable "profile" { type = string  default = "dev-windows" }

source "hyperv-vmcx" "ingress" {
  clone_from_vmcx_path = "output/base-debian12"
  output_directory     = "output/role-ingress"
  cpus = 2  memory = 2048
}
source "qemu" "ingress" {
  iso_url          = "output/base-debian12/base-debian12.qcow2"
  iso_checksum     = "none"
  disk_image       = true
  use_backing_file = true
  format           = "qcow2"
  output_directory = "output/role-ingress"
  ssh_username     = "bhb"  ssh_timeout = "20m"
  shutdown_command = "sudo systemctl poweroff"
}
build {
  sources = ["source.hyperv-vmcx.ingress", "source.qemu.ingress"]
  provisioner "shell" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y --no-install-recommends nginx",
      "sudo cloud-init clean --logs"
    ]
  }
}
