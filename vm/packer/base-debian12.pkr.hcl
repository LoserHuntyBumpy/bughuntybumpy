# Golden Base: Debian 12 netinst + cloud-init, cloud-init-ready, gehaertet.
# Zwei Builder, gleicher Provisioner-Pfad (Profil dev-windows | prod-linux).
# Determinismus: unattended-upgrades AUS, apt gegen snapshot.debian.org gepinnt
# (Plan Risiko Image-Drift / env_hash).

packer {
  required_plugins {
    hyperv = { source = "github.com/hashicorp/hyperv", version = ">= 1.1.0" }
    qemu   = { source = "github.com/hashicorp/qemu",   version = ">= 1.1.0" }
  }
}

variable "profile" { type = string  default = "dev-windows" }
variable "debian_iso_url"      { type = string  default = "https://cdimage.debian.org/cdimage/release/12.5.0/amd64/iso-cd/debian-12.5.0-amd64-netinst.iso" }
variable "debian_iso_checksum" { type = string  default = "sha256:0openssl_pin_here" }
variable "ssh_pubkey"          { type = string  default = "" }

source "hyperv-iso" "base" {
  iso_url           = var.debian_iso_url
  iso_checksum      = var.debian_iso_checksum
  cpus              = 2
  memory            = 2048
  disk_size         = 12288
  generation        = 2
  switch_name       = "Default Switch"
  http_directory    = "http"
  boot_command      = ["<esc><wait>auto preseed/url=http://{{.HTTPIP}}:{{.HTTPPort}}/preseed.cfg<enter>"]
  ssh_username      = "bhb"
  ssh_timeout       = "30m"
  shutdown_command  = "sudo systemctl poweroff"
  output_directory  = "output/base-debian12"
}

source "qemu" "base" {
  iso_url          = var.debian_iso_url
  iso_checksum     = var.debian_iso_checksum
  cpus             = 2
  memory           = 2048
  disk_size        = "12288M"
  format           = "qcow2"
  accelerator      = "kvm"
  http_directory   = "http"
  boot_command     = ["<esc><wait>auto preseed/url=http://{{.HTTPIP}}:{{.HTTPPort}}/preseed.cfg<enter>"]
  ssh_username     = "bhb"
  ssh_timeout      = "30m"
  shutdown_command = "sudo systemctl poweroff"
  output_directory = "output/base-debian12"
}

build {
  sources = ["source.hyperv-iso.base", "source.qemu.base"]

  provisioner "shell" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y --no-install-recommends cloud-init qemu-guest-agent python3 python3-venv",
      "sudo systemctl disable apt-daily.timer apt-daily-upgrade.timer || true",
      "sudo cloud-init clean --logs",
      "sudo truncate -s 0 /etc/machine-id"
    ]
  }
}
