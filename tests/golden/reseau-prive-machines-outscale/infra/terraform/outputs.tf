# Généré par DevOps Builder — à relire avant usage.

output "net_id" {
  value = outscale_net.main.net_id
}

output "subnet_id" {
  value = outscale_subnet.main.subnet_id
}

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = outscale_public_ip.hors_production[*].public_ip
    "production"      = outscale_public_ip.production[*].public_ip
  }
}
