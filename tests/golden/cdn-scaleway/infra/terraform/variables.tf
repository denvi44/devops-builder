# Généré par DevOps Builder — à relire avant usage.

variable "ssh_public_key" {
  type        = string
  description = "Clé SSH publique du compte de déploiement (moitié publique de SSH_PRIVATE_KEY)"
}

variable "cdn_origin" {
  type        = string
  description = "Nom d'hôte public de l'application, vers lequel le CDN renvoie les requêtes"
  default     = ""
}
