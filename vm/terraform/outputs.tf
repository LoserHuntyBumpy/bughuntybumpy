# IPs / SSH-Endpunkte + Ansible-Inventory-Generator (von 020_provision_stack.ps1
# in vm/ansible/inventory.tf-generated.ini geschrieben).

output "ingress_ip" {
  value = "10.20.0.2"   # statisch via cloud-init; bei NAT ueber Hypervisor-DHCP ableitbar
}

output "ansible_inventory" {
  value = <<-EOT
    [ingress]
    vm-ingress ansible_host=10.20.0.2
    [app]
    vm-app ansible_host=10.20.0.10
    [data]
    vm-data ansible_host=10.20.0.20
    [broker]
    vm-broker ansible_host=10.20.0.30
    [all:vars]
    ansible_user=bhb
  EOT
}
