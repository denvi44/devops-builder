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
    name           = "default"
    node_count     = 2
    vm_size        = "Standard_D2s_v5"
    vnet_subnet_id = azurerm_subnet.aks.id
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "azure"
    service_cidr   = "172.31.0.0/16"
    dns_service_ip = "172.31.0.10"
  }
}

# --- Azure Blob Storage
# Le compte de stockage de l'état est créé hors de cette pile (amorçage), région francecentral.

# --- Azure Virtual Network
resource "azurerm_virtual_network" "main" {
  name                = "vnet-mon-app"
  address_space       = ["10.20.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_subnet" "aks" {
  name                 = "snet-aks"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.20.4.0/22"]
}

# Bases managées : sous-réseau délégué aux serveurs flexibles, zone DNS privée pour leur nom.
resource "azurerm_subnet" "data" {
  name                 = "snet-data"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.20.3.0/24"]

  delegation {
    name = "flexible-server"

    service_delegation {
      name    = "Microsoft.DBforMySQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "data" {
  name                = "privatelink.mysql.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "data" {
  name                  = "vnet-mon-app"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.data.name
  virtual_network_id    = azurerm_virtual_network.main.id
}

# --- Azure Database (serveur flexible) (Préproduction)
resource "random_password" "db_staging" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "azurerm_mysql_flexible_server" "db_staging" {
  name                   = "mon-app-db-staging"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "8.0.21"
  administrator_login    = "app"
  administrator_password = random_password.db_staging.result
  sku_name               = "B_Standard_B1ms"
  backup_retention_days  = 7
  delegated_subnet_id    = azurerm_subnet.data.id
  private_dns_zone_id    = azurerm_private_dns_zone.data.id

  depends_on = [azurerm_private_dns_zone_virtual_network_link.data]
}

resource "azurerm_mysql_flexible_database" "db_staging" {
  name                = "app"
  resource_group_name = azurerm_resource_group.main.name
  server_name         = azurerm_mysql_flexible_server.db_staging.name
  charset             = "utf8mb4"
  collation           = "utf8mb4_unicode_ci"
}

# --- Azure Database (serveur flexible) (Production)
resource "random_password" "db_production" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "azurerm_mysql_flexible_server" "db_production" {
  name                   = "mon-app-db"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "8.0.21"
  administrator_login    = "app"
  administrator_password = random_password.db_production.result
  sku_name               = "B_Standard_B1ms"
  backup_retention_days  = 14
  delegated_subnet_id    = azurerm_subnet.data.id
  private_dns_zone_id    = azurerm_private_dns_zone.data.id

  depends_on = [azurerm_private_dns_zone_virtual_network_link.data]
}

resource "azurerm_mysql_flexible_database" "db_production" {
  name                = "app"
  resource_group_name = azurerm_resource_group.main.name
  server_name         = azurerm_mysql_flexible_server.db_production.name
  charset             = "utf8mb4"
  collation           = "utf8mb4_unicode_ci"
}
