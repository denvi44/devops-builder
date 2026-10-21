# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = scaleway_instance_ip.hors_production[*].address
    "production"      = scaleway_instance_ip.production[*].address
  }
}

output "fn_staging_url" {
  description = "Adresse HTTPS de la fonction"
  value       = "https://${scaleway_function.fn_staging.domain_name}"
}

output "fn_production_url" {
  description = "Adresse HTTPS de la fonction"
  value       = "https://${scaleway_function.fn_production.domain_name}"
}
