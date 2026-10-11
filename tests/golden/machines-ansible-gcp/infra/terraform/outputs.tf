# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = [for vm in google_compute_instance.hors_production : vm.network_interface[0].access_config[0].nat_ip]
    "production"      = [for vm in google_compute_instance.production : vm.network_interface[0].access_config[0].nat_ip]
  }
}
