# Généré par DevOps Builder — à relire avant usage.

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "registry" {
  value = aws_ecr_repository.app.repository_url
}

output "db_staging_endpoint" {
  value = aws_db_instance.db_staging.address
}

output "db_staging_secret_arn" {
  description = "Secret Secrets Manager du mot de passe principal"
  value       = aws_db_instance.db_staging.master_user_secret[0].secret_arn
}

output "db_production_endpoint" {
  value = aws_db_instance.db_production.address
}

output "db_production_secret_arn" {
  description = "Secret Secrets Manager du mot de passe principal"
  value       = aws_db_instance.db_production.master_user_secret[0].secret_arn
}
