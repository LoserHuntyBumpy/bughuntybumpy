# Deklarative Stack-Erzeugung: 3 Switches + 4 Rollen-VMs je Profil.
# Provider-Wahl ueber var.profile (count-Gate). Gleiche Topologie, zwei
# Hypervisoren (Plan §3). Runner-VMs erzeugt der Broker zur Laufzeit
# (nicht Terraform) — ephemer, Linked Clone.

terraform {
  required_providers {
    hyperv  = { source = "taliesins/hyperv", version = ">= 1.2.1" }
    libvirt = { source = "dmacvicar/libvirt", version = ">= 0.7.6" }
  }
}

locals {
  is_win = var.profile == "dev-windows"
  roles = {
    ingress = { mem = 2147483648, cpu = 2, nets = ["ext", "svc"] }
    app     = { mem = 4294967296, cpu = 2, nets = ["svc"] }
    data    = { mem = 4294967296, cpu = 2, nets = ["svc"] }
    broker  = { mem = 2147483648, cpu = 2, nets = ["svc"] }
  }
}

# ---------- Profil dev-windows (Hyper-V) ----------
provider "hyperv" {}

resource "hyperv_network_switch" "win" {
  for_each   = local.is_win ? var.switches : {}
  name       = "bhb-${each.key}-switch"
  switch_type = each.value.uplink ? "External" : "Private"
}

resource "hyperv_machine_instance" "win" {
  for_each            = local.is_win ? local.roles : {}
  name                = "vm-${each.key}"
  generation          = 2
  processor_count     = each.value.cpu
  static_memory       = true
  memory_startup_bytes = each.value.mem
  dynamic "network_adaptors" {
    for_each = each.value.nets
    content {
      name        = network_adaptors.value
      switch_name = "bhb-${network_adaptors.value}-switch"
    }
  }
  hard_disk_drives {
    path = "${var.image_dir}/role-${each.key}/vm-${each.key}.vhdx"
  }
  depends_on = [hyperv_network_switch.win]
}

# ---------- Profil prod-linux (libvirt) ----------
provider "libvirt" { uri = "qemu:///system" }

resource "libvirt_network" "lin" {
  for_each = local.is_win ? {} : var.switches
  name     = "bhb-${each.key}"
  mode     = each.value.uplink ? "nat" : "none"
  autostart = true
}

resource "libvirt_volume" "lin" {
  for_each = local.is_win ? {} : local.roles
  name     = "vm-${each.key}.qcow2"
  source   = "${var.image_dir}/role-${each.key}/role-${each.key}.qcow2"
  format   = "qcow2"
}

resource "libvirt_domain" "lin" {
  for_each = local.is_win ? {} : local.roles
  name     = "vm-${each.key}"
  memory   = each.value.mem / 1048576
  vcpu     = each.value.cpu
  disk { volume_id = libvirt_volume.lin[each.key].id }
  dynamic "network_interface" {
    for_each = each.value.nets
    content { network_name = "bhb-${network_interface.value}" }
  }
}
