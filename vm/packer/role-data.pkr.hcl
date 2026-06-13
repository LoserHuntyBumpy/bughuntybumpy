# Rollen-Image data: postgres, redis, minio (native Pakete / minio-Binary).
variable "profile" { type = string  default = "dev-windows" }

source "hyperv-vmcx" "data" {
  clone_from_vmcx_path = "output/base-debian12"
  output_directory     = "output/role-data"
  cpus = 2  memory = 4096
}
source "qemu" "data" {
  iso_url          = "output/base-debian12/base-debian12.qcow2"
  iso_checksum     = "none"
  disk_image       = true
  use_backing_file = true
  format           = "qcow2"
  output_directory = "output/role-data"
  ssh_username     = "bhb"  ssh_timeout = "20m"
  shutdown_command = "sudo systemctl poweroff"
}
build {
  sources = ["source.hyperv-vmcx.data", "source.qemu.data"]
  provisioner "shell" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y --no-install-recommends postgresql redis-server",
      "curl -fsSL https://dl.min.io/server/minio/release/linux-amd64/minio -o /tmp/minio && sudo install /tmp/minio /usr/local/bin/minio",
      "sudo cloud-init clean --logs"
    ]
  }
}
