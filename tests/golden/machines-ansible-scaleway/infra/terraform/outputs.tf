# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = scaleway_instance_ip.hors_production[*].address
    "production"      = scaleway_instance_ip.production[*].address
  }
}
