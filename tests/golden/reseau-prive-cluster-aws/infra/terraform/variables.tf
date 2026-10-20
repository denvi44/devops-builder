# Généré par DevOps Builder — à relire avant usage.

variable "ci_deploy_role_arn" {
  type        = string
  description = "Rôle de déploiement de la CI (AWS_ROLE_ARN), autorisé sur le cluster ; vide = aucun"
  default     = ""
}

variable "cluster_admin_arns" {
  type        = list(string)
  description = "Rôles ou utilisateurs IAM des personnes qui administrent le cluster"
  default     = []
}
