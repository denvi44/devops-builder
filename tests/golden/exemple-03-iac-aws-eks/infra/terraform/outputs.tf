# Généré par DevOps Builder — à relire avant usage.

output "cluster_staging_name" {
  value = module.eks_staging.cluster_name
}

output "cluster_staging_endpoint" {
  value = module.eks_staging.cluster_endpoint
}

output "cluster_production_name" {
  value = module.eks_production.cluster_name
}

output "cluster_production_endpoint" {
  value = module.eks_production.cluster_endpoint
}

output "registry" {
  value = aws_ecr_repository.app.repository_url
}

output "eso_role_arn" {
  description = "Rôle IAM du contrôleur External Secrets (Pod Identity)"
  value       = aws_iam_role.external_secrets.arn
}
