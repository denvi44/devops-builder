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

# SonarQube : SAML (son édition Community ne parle pas OIDC)
resource "keycloak_saml_client" "sonarqube" {
  realm_id                  = keycloak_realm.main.id
  client_id                 = "sonarqube"
  name                      = "SonarQube"
  sign_documents            = true
  sign_assertions           = true
  client_signature_required = false
  name_id_format            = "username"
  valid_redirect_uris       = ["${var.sonarqube_url}/oauth2/callback/saml"]
  base_url                  = var.sonarqube_url
}

resource "keycloak_saml_user_property_protocol_mapper" "sonarqube_login" {
  realm_id                   = keycloak_realm.main.id
  client_id                  = keycloak_saml_client.sonarqube.id
  name                       = "login"
  user_property              = "username"
  saml_attribute_name        = "login"
  saml_attribute_name_format = "Basic"
}

resource "keycloak_saml_user_property_protocol_mapper" "sonarqube_name" {
  realm_id                   = keycloak_realm.main.id
  client_id                  = keycloak_saml_client.sonarqube.id
  name                       = "name"
  user_property              = "firstName"
  saml_attribute_name        = "name"
  saml_attribute_name_format = "Basic"
}

resource "keycloak_saml_user_property_protocol_mapper" "sonarqube_email" {
  realm_id                   = keycloak_realm.main.id
  client_id                  = keycloak_saml_client.sonarqube.id
  name                       = "email"
  user_property              = "email"
  saml_attribute_name        = "email"
  saml_attribute_name_format = "Basic"
}

resource "keycloak_generic_protocol_mapper" "sonarqube_groups" {
  realm_id        = keycloak_realm.main.id
  client_id       = keycloak_saml_client.sonarqube.id
  name            = "groups"
  protocol        = "saml"
  protocol_mapper = "saml-group-membership-mapper"
  config = {
    "attribute.name"       = "groups"
    "attribute.nameformat" = "Basic"
    "full.path"            = "false"
    "single"               = "true"
  }
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
