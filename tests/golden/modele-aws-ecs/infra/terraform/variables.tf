# Généré par DevOps Builder — à relire avant usage.

variable "db_subnet_group" {
  type        = string
  description = "Groupe de sous-réseaux privés des instances RDS"
}

variable "db_security_group_ids" {
  type        = list(string)
  description = "Groupes de sécurité autorisant l'application à joindre la base"
}
