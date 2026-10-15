# Généré par DevOps Builder — à relire avant usage.

output "issuer" {
  value = "https://auth.boutique.fr/realms/mon-app"
}

output "grafana_client_secret" {
  value     = keycloak_openid_client.grafana.client_secret
  sensitive = true
}
