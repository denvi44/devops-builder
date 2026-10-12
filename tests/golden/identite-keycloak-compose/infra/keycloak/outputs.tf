# Généré par DevOps Builder — à relire avant usage.

output "issuer" {
  value = "https://auth.boutique.fr/realms/mon-app"
}

output "openbao_client_secret" {
  value     = keycloak_openid_client.openbao.client_secret
  sensitive = true
}

output "grafana_client_secret" {
  value     = keycloak_openid_client.grafana.client_secret
  sensitive = true
}
