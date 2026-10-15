# Généré par DevOps Builder — à relire avant usage.

variable "vpc_id" {
  type        = string
  description = "VPC du cluster EKS"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Sous-réseaux privés du cluster"
}

variable "db_subnet_group" {
  type        = string
  description = "Groupe de sous-réseaux privés des instances RDS"
}

variable "db_security_group_ids" {
  type        = list(string)
  description = "Groupes de sécurité autorisant l'application à joindre la base"
}

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
