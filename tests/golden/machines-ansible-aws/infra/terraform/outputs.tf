# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = aws_instance.hors_production[*].public_ip
    "production"      = aws_instance.production[*].public_ip
  }
}
