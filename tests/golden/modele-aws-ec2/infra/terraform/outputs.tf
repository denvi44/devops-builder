# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "staging"    = aws_instance.staging[*].public_ip
    "production" = aws_instance.production[*].public_ip
  }
}
