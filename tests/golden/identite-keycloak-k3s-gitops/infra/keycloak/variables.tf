# Généré par DevOps Builder — à relire avant usage.

variable "keycloak_url" {
  type        = string
  description = "Adresse de Keycloak"
  default     = "https://auth.boutique.fr"
}

variable "app_url" {
  type        = string
  description = "Adresse publique de l'application"
  default     = "https://boutique.fr"
}

variable "openbao_url" {
  type        = string
  description = "Adresse de OpenBao"
  default     = "https://openbao.boutique.fr"
}

variable "argocd_url" {
  type        = string
  description = "Adresse de Argo CD"
  default     = "https://argocd.boutique.fr"
}

variable "grafana_url" {
  type        = string
  description = "Adresse de Grafana"
  default     = "https://grafana.boutique.fr"
}
