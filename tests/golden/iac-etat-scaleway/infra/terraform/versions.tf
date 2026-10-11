# Généré par DevOps Builder — à relire avant usage.
terraform {
  required_version = ">= 1.10"

  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.0"
    }
  }

  # Scaleway Object Storage : clés S3 dans AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (posées par la CI).
  # Pas de verrou d'état : la CI sérialise les apply.
  backend "s3" {
    bucket                      = "mon-projet-tfstate"
    key                         = "mon-app/terraform.tfstate"
    region                      = "fr-par"
    endpoints                   = { s3 = "https://s3.fr-par.scw.cloud" }
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
  }
}
