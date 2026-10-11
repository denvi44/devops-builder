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
