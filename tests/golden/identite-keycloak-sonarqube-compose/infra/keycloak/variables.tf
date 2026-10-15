# Généré par DevOps Builder — à relire avant usage.

variable "keycloak_url" {
  type        = string
  description = "Adresse de Keycloak"
  default     = "https://auth.boutique.fr"
}

variable "app_url" {
  type        = string
  description = "Adresse publique de l'application"
  default     = "https://app.example.com"
}

variable "grafana_url" {
  type        = string
  description = "Adresse de Grafana"
  default     = "https://grafana.boutique.fr"
}

variable "sonarqube_url" {
  type        = string
  description = "Adresse de SonarQube"
  default     = "https://sonarqube.boutique.fr"
}
