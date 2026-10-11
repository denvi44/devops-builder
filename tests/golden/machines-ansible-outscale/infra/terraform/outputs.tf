# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = outscale_public_ip.hors_production[*].public_ip
    "production"      = outscale_public_ip.production[*].public_ip
  }
}
