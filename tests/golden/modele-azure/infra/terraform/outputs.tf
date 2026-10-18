# Généré par DevOps Builder — à relire avant usage.

output "cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "registry" {
  value = azurerm_container_registry.main.login_server
}

output "db_staging_host" {
  value = azurerm_postgresql_flexible_server.db_staging.fqdn
}

output "db_staging_password" {
  value     = random_password.db_staging.result
  sensitive = true
}

output "db_production_host" {
  value = azurerm_postgresql_flexible_server.db_production.fqdn
}

output "db_production_password" {
  value     = random_password.db_production.result
  sensitive = true
}

output "eso_client_id" {
  description = "Identité managée du contrôleur External Secrets"
  value       = azurerm_user_assigned_identity.external_secrets.client_id
}

output "eso_tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}
