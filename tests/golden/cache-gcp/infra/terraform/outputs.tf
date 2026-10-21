# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = [for vm in google_compute_instance.hors_production : vm.network_interface[0].access_config[0].nat_ip]
    "production"      = [for vm in google_compute_instance.production : vm.network_interface[0].access_config[0].nat_ip]
  }
}

output "cache_gcp_staging_host" {
  value = google_redis_instance.cache_gcp_staging.host
}

output "cache_gcp_staging_password" {
  value     = google_redis_instance.cache_gcp_staging.auth_string
  sensitive = true
}

output "cache_gcp_production_host" {
  value = google_redis_instance.cache_gcp_production.host
}

output "cache_gcp_production_password" {
  value     = google_redis_instance.cache_gcp_production.auth_string
  sensitive = true
}
