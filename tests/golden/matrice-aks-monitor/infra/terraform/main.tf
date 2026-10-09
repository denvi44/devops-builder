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

# --- Azure Kubernetes Service
resource "azurerm_kubernetes_cluster" "main" {
  name                = "mon-cluster"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "mon-app"

  default_node_pool {
    name       = "default"
    node_count = 2
    vm_size    = "Standard_D2s_v5"
  }

  identity {
    type = "SystemAssigned"
  }

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }
}

# --- Azure Monitor (Container Insights)
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-mon-app"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

# --- Azure Blob Storage
# Le compte de stockage de l'état est créé hors de cette pile (amorçage), région francecentral.
