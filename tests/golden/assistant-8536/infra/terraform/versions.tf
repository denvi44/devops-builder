# Généré par DevOps Builder — à relire avant usage.
terraform {
  required_version = ">= 1.6"

  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.0"
    }
  }

  # Backend local : ajouter un stockage objet (S3, GCS, Blob) pour partager l'état.
}
