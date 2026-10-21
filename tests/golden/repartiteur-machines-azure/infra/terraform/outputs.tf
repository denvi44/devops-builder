# Généré par DevOps Builder — à relire avant usage.

output "vnet_id" {
  value = azurerm_virtual_network.main.id
}

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = azurerm_public_ip.hors_production[*].ip_address
    "production"      = azurerm_public_ip.production[*].ip_address
  }
}

output "lb_hors_production" {
  description = "Adresse IP du répartiteur de hors-production"
  value       = azurerm_public_ip.lb_hors_production.ip_address
}

output "lb_production" {
  description = "Adresse IP du répartiteur de production"
  value       = azurerm_public_ip.lb_production.ip_address
}
