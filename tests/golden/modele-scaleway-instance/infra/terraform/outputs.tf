# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "staging"    = scaleway_instance_ip.staging[*].address
    "production" = scaleway_instance_ip.production[*].address
  }
}
