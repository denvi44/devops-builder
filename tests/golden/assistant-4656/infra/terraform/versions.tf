# Généré par DevOps Builder — à relire avant usage.
terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "mon-projet-tfstate"
    key    = "mon-app/terraform.tfstate"
    region = "eu-west-3"
  }
}
