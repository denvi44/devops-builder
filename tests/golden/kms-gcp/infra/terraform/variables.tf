# Généré par DevOps Builder — à relire avant usage.

variable "ssh_public_key" {
  type        = string
  description = "Clé SSH publique du compte de déploiement (moitié publique de SSH_PRIVATE_KEY)"
}

variable "gcp_project_id" {
  type    = string
  default = "mon-projet"
}
