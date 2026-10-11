# Généré par DevOps Builder — à relire avant usage.
terraform {
  required_version = ">= 1.10"

  required_providers {
    ovh = {
      source  = "ovh/ovh"
      version = "~> 2.0"
    }
  }

  # Backend local : ajouter un stockage objet du fournisseur pour partager l'état entre les jobs (R44).
}
