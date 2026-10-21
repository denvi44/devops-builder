# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = outscale_public_ip.hors_production[*].public_ip
    "production"      = outscale_public_ip.production[*].public_ip
  }
}

output "lb_hors_production" {
  description = "Nom DNS du répartiteur de hors-production"
  value       = outscale_load_balancer.hors_production.dns_name
}

output "lb_production" {
  description = "Nom DNS du répartiteur de production"
  value       = outscale_load_balancer.production.dns_name
}
