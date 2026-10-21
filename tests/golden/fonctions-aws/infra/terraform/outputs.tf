# Généré par DevOps Builder — à relire avant usage.

output "registry" {
  value = aws_ecr_repository.app.repository_url
}

output "fn_staging_url" {
  description = "Adresse HTTPS de la fonction"
  value       = aws_lambda_function_url.fn_staging.function_url
}

output "fn_production_url" {
  description = "Adresse HTTPS de la fonction"
  value       = aws_lambda_function_url.fn_production.function_url
}
