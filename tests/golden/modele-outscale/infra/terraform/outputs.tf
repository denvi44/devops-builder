# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "staging"    = outscale_public_ip.staging[*].public_ip
    "production" = outscale_public_ip.production[*].public_ip
  }
}
