# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = scaleway_instance_ip.hors_production[*].address
    "production"      = scaleway_instance_ip.production[*].address
  }
}

output "cache_scaleway_staging_host" {
  value = scaleway_redis_cluster.cache_scaleway_staging.public_network[0].ips[0]
}

output "cache_scaleway_staging_password" {
  value     = random_password.cache_scaleway_staging.result
  sensitive = true
}

output "cache_scaleway_production_host" {
  value = scaleway_redis_cluster.cache_scaleway_production.public_network[0].ips[0]
}

output "cache_scaleway_production_password" {
  value     = random_password.cache_scaleway_production.result
  sensitive = true
}
