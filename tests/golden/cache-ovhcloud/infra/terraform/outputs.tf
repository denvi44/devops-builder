# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = [for vm in ovh_cloud_project_instance.hors_production : [for a in vm.addresses : a.ip if a.version == 4][0]]
    "production"      = [for vm in ovh_cloud_project_instance.production : [for a in vm.addresses : a.ip if a.version == 4][0]]
  }
}

output "cache_ovh_staging_endpoints" {
  value = ovh_cloud_project_database.cache_ovh_staging.endpoints
}

output "cache_ovh_staging_password" {
  value     = ovh_cloud_project_database_valkey_user.cache_ovh_staging.password
  sensitive = true
}

output "cache_ovh_production_endpoints" {
  value = ovh_cloud_project_database.cache_ovh_production.endpoints
}

output "cache_ovh_production_password" {
  value     = ovh_cloud_project_database_valkey_user.cache_ovh_production.password
  sensitive = true
}
