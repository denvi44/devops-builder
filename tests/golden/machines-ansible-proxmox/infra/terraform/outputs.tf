# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = [for vm in proxmox_virtual_environment_vm.hors_production : vm.ipv4_addresses[1][0]]
    "production"      = [for vm in proxmox_virtual_environment_vm.production : vm.ipv4_addresses[1][0]]
  }
}
