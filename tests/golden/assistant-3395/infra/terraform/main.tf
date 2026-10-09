# Généré par DevOps Builder — à relire avant usage.

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "main" {
  name     = "rg-mon-app"
  location = "francecentral"
}

# --- Azure Container Registry
resource "azurerm_container_registry" "main" {
  name                = "monappregistry"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
}

# --- Azure Blob Storage
# Le compte de stockage de l'état est créé hors de cette pile (amorçage), région francecentral.

# --- Azure Container Apps
# Azure Container Apps : ajouter azurerm_container_app_environment et azurerm_container_app.
