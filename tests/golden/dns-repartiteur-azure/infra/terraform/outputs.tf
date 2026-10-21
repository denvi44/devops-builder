# Généré par DevOps Builder — à relire avant usage.

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

output "dns_name_servers" {
  description = "Serveurs de noms à indiquer chez le registrar du domaine"
  value       = azurerm_dns_zone.main.name_servers
}
