# Généré par DevOps Builder — à relire avant usage.
terraform {
  required_version = ">= 1.10"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-mon-app"
    storage_account_name = "monprojettfstate"
    container_name       = "tfstate"
    key                  = "mon-app.tfstate"
  }
}
