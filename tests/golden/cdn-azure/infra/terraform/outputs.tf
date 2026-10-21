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

output "cdn_hostname" {
  description = "Nom d'hôte du CDN (Front Door)"
  value       = azurerm_cdn_frontdoor_endpoint.main.host_name
}
