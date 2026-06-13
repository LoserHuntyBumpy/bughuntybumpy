variable "profile" {
  type        = string
  default     = "dev-windows"        # dev-windows (Hyper-V) | prod-linux (libvirt)
  validation {
    condition     = contains(["dev-windows", "prod-linux"], var.profile)
    error_message = "profile muss dev-windows oder prod-linux sein."
  }
}

variable "image_dir" {
  type    = string
  default = "../output"              # Packer-Output (Golden + Rollen)
}

variable "ssh_pubkey" {
  type    = string
  default = ""
}

# Netz-Mapping docker-network -> Hypervisor-Switch (Plan §2)
variable "switches" {
  type = map(object({ uplink = bool }))
  default = {
    ext     = { uplink = true }      # frontend  -> External/NAT (einziger Internet-Pfad)
    svc     = { uplink = false }     # backend   -> Internal/Host-Only (App<->DB)
    sandbox = { uplink = false }     # sandbox   -> Private, kein Host-Adapter, kein Egress
  }
}
