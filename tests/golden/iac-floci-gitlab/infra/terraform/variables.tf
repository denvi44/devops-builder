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
