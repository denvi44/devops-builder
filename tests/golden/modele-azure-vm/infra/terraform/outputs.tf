# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "staging"    = azurerm_public_ip.staging[*].ip_address
    "production" = azurerm_public_ip.production[*].ip_address
  }
}
