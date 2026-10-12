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
  default     = "https://coffre.boutique.fr"
}

variable "grafana_url" {
  type        = string
  description = "Adresse de Grafana"
  default     = "https://grafana.boutique.fr"
}
