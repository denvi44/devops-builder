# Généré par DevOps Builder — à relire avant usage.

output "cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "registry" {
  value = azurerm_container_registry.main.login_server
}

output "vnet_id" {
  value = azurerm_virtual_network.main.id
}

output "db_staging_host" {
  value = azurerm_mysql_flexible_server.db_staging.fqdn
}

output "db_staging_password" {
  value     = random_password.db_staging.result
  sensitive = true
}

output "db_production_host" {
  value = azurerm_mysql_flexible_server.db_production.fqdn
}

output "db_production_password" {
  value     = random_password.db_production.result
  sensitive = true
}
