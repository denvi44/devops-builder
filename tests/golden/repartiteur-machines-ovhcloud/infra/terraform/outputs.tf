# Généré par DevOps Builder — à relire avant usage.

output "private_network_id" {
  value = ovh_cloud_project_network_private.main.id
}

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = [for vm in ovh_cloud_project_instance.hors_production : [for a in vm.addresses : a.ip if a.version == 4][0]]
    "production"      = [for vm in ovh_cloud_project_instance.production : [for a in vm.addresses : a.ip if a.version == 4][0]]
  }
}

output "lb_hors_production" {
  description = "Identifiant du répartiteur de hors-production"
  value       = ovh_cloud_loadbalancer.hors_production.id
}

output "lb_production" {
  description = "Identifiant du répartiteur de production"
  value       = ovh_cloud_loadbalancer.production.id
}
