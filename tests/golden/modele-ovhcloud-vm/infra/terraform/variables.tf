# Généré par DevOps Builder — à relire avant usage.

variable "ssh_public_key" {
  type        = string
  description = "Clé SSH publique du compte de déploiement (moitié publique de SSH_PRIVATE_KEY)"
}

variable "ovh_service_name" {
  type        = string
  description = "Identifiant du projet Public Cloud OVHcloud"
  default     = "<id-projet-public-cloud>"
}
