# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = aws_instance.hors_production[*].public_ip
    "production"      = aws_instance.production[*].public_ip
  }
}

output "cache_aws_staging_endpoint" {
  value = aws_elasticache_replication_group.cache_aws_staging.primary_endpoint_address
}

output "cache_aws_staging_password" {
  value     = random_password.cache_aws_staging.result
  sensitive = true
}

output "cache_aws_production_endpoint" {
  value = aws_elasticache_replication_group.cache_aws_production.primary_endpoint_address
}

output "cache_aws_production_password" {
  value     = random_password.cache_aws_production.result
  sensitive = true
}
