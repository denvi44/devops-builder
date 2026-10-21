# Généré par DevOps Builder — à relire avant usage.

output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = aws_instance.hors_production[*].public_ip
    "production"      = aws_instance.production[*].public_ip
  }
}

output "lb_hors_production" {
  description = "Adresse DNS du répartiteur de hors-production"
  value       = aws_lb.hors_production.dns_name
}

output "lb_production" {
  description = "Adresse DNS du répartiteur de production"
  value       = aws_lb.production.dns_name
}
