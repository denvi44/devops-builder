# Généré par DevOps Builder — à relire avant usage.

output "registry" {
  value = azurerm_container_registry.main.login_server
}

output "fn_staging_url" {
  description = "Adresse HTTPS de l'application de fonctions"
  value       = "https://${azurerm_linux_function_app.fn_staging.default_hostname}"
}

output "fn_production_url" {
  description = "Adresse HTTPS de l'application de fonctions"
  value       = "https://${azurerm_linux_function_app.fn_production.default_hostname}"
}
