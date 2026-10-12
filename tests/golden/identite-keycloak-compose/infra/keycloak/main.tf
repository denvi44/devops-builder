# Généré par DevOps Builder — à relire avant usage.

resource "keycloak_realm" "main" {
  realm                    = "mon-app"
  display_name             = "Mon projet"
  enabled                  = true
  login_with_email_allowed = true
  ssl_required             = "external"
  password_policy          = "length(12) and notUsername"
}

resource "keycloak_group" "admins" {
  realm_id = keycloak_realm.main.id
  name     = "admins"
}

resource "keycloak_group" "developpeurs" {
  realm_id = keycloak_realm.main.id
  name     = "developpeurs"
}

# Revendication « groups » : les outils donnent les droits d'après les groupes

resource "keycloak_openid_client_scope" "groups" {
  realm_id               = keycloak_realm.main.id
  name                   = "groups"
  include_in_token_scope = true
}

resource "keycloak_openid_group_membership_protocol_mapper" "groups" {
  realm_id        = keycloak_realm.main.id
  client_scope_id = keycloak_openid_client_scope.groups.id
  name            = "groups"
  claim_name      = "groups"
  full_path       = false
}

# Application : client public, PKCE, sans secret
resource "keycloak_openid_client" "app" {
  realm_id                        = keycloak_realm.main.id
  client_id                       = "mon-app"
  name                            = "Mon projet"
  access_type                     = "PUBLIC"
  standard_flow_enabled           = true
  pkce_code_challenge_method      = "S256"
  valid_redirect_uris             = ["${var.app_url}/*"]
  valid_post_logout_redirect_uris = ["${var.app_url}/*"]
  web_origins                     = [var.app_url]
}

resource "keycloak_openid_client_default_scopes" "app" {
  realm_id       = keycloak_realm.main.id
  client_id      = keycloak_openid_client.app.id
  default_scopes = ["profile", "email", "roles", "web-origins", keycloak_openid_client_scope.groups.name]
}

resource "keycloak_openid_client" "openbao" {
  realm_id              = keycloak_realm.main.id
  client_id             = "openbao"
  name                  = "OpenBao"
  access_type           = "CONFIDENTIAL"
  standard_flow_enabled = true
  valid_redirect_uris   = ["${var.openbao_url}/ui/vault/auth/oidc/oidc/callback", "http://localhost:8250/oidc/callback"]
  base_url              = var.openbao_url
}

resource "keycloak_openid_client_default_scopes" "openbao" {
  realm_id       = keycloak_realm.main.id
  client_id      = keycloak_openid_client.openbao.id
  default_scopes = ["profile", "email", "roles", "web-origins", keycloak_openid_client_scope.groups.name]
}

resource "keycloak_openid_client" "grafana" {
  realm_id              = keycloak_realm.main.id
  client_id             = "grafana"
  name                  = "Grafana"
  access_type           = "CONFIDENTIAL"
  standard_flow_enabled = true
  valid_redirect_uris   = ["${var.grafana_url}/login/generic_oauth"]
  base_url              = var.grafana_url
}

resource "keycloak_openid_client_default_scopes" "grafana" {
  realm_id       = keycloak_realm.main.id
  client_id      = keycloak_openid_client.grafana.id
  default_scopes = ["profile", "email", "roles", "web-origins", keycloak_openid_client_scope.groups.name]
}
