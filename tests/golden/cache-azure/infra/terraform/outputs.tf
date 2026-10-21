# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = azurerm_public_ip.hors_production[*].ip_address
    "production"      = azurerm_public_ip.production[*].ip_address
  }
}

output "cache_azure_staging_host" {
  value = azurerm_redis_cache.cache_azure_staging.hostname
}

output "cache_azure_staging_password" {
  value     = azurerm_redis_cache.cache_azure_staging.primary_access_key
  sensitive = true
}

output "cache_azure_production_host" {
  value = azurerm_redis_cache.cache_azure_production.hostname
}

output "cache_azure_production_password" {
  value     = azurerm_redis_cache.cache_azure_production.primary_access_key
  sensitive = true
}
