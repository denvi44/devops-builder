# Généré par DevOps Builder — à relire avant usage.

variable "vpc_id" {
  type        = string
  description = "VPC du cluster EKS"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Sous-réseaux privés du cluster"
}
