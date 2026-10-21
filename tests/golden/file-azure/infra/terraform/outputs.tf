# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = azurerm_public_ip.hors_production[*].ip_address
    "production"      = azurerm_public_ip.production[*].ip_address
  }
}

output "queue_staging_url" {
  description = "Espace de noms Service Bus et nom de la file"
  value       = "${azurerm_servicebus_namespace.main.name}.servicebus.windows.net/${azurerm_servicebus_queue.queue_staging.name}"
}

output "queue_production_url" {
  description = "Espace de noms Service Bus et nom de la file"
  value       = "${azurerm_servicebus_namespace.main.name}.servicebus.windows.net/${azurerm_servicebus_queue.queue_production.name}"
}
