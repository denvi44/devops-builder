# Généré par DevOps Builder — à relire avant usage.
# Realm « mon-app » : comptes, groupes et clients OIDC. Appliqué à part de l'infrastructure,
# une fois Keycloak démarré (docs/mise-en-route.md) ; le provider lit KEYCLOAK_USER et
# KEYCLOAK_PASSWORD (administrateur du realm master) dans l'environnement.
terraform {
  required_version = ">= 1.10"

  required_providers {
    keycloak = {
      source  = "keycloak/keycloak"
      version = "~> 5.10"
    }
  }
}

provider "keycloak" {
  url       = var.keycloak_url
  client_id = "admin-cli"
}
