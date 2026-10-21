# Généré par DevOps Builder — à relire avant usage.

output "network" {
  value = google_compute_network.main.name
}

output "subnetwork" {
  value = google_compute_subnetwork.main.name
}

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = [for vm in google_compute_instance.hors_production : vm.network_interface[0].access_config[0].nat_ip]
    "production"      = [for vm in google_compute_instance.production : vm.network_interface[0].access_config[0].nat_ip]
  }
}

output "lb_hors_production" {
  description = "Adresse IP du répartiteur de hors-production"
  value       = google_compute_address.lb_hors_production.address
}

output "lb_production" {
  description = "Adresse IP du répartiteur de production"
  value       = google_compute_address.lb_production.address
}
