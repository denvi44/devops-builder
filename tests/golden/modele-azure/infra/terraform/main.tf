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

  oidc_issuer_enabled       = true
  workload_identity_enabled = true
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

# --- Azure Key Vault
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                      = "kv-mon-app"
  location                  = azurerm_resource_group.main.location
  resource_group_name       = azurerm_resource_group.main.name
  tenant_id                 = data.azurerm_client_config.current.tenant_id
  sku_name                  = "standard"
  enable_rbac_authorization = true
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

resource "azurerm_postgresql_flexible_server" "db_staging" {
  name                   = "mon-app-db-staging"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "16"
  administrator_login    = "app"
  administrator_password = random_password.db_staging.result
  sku_name               = "B_Standard_B1ms"
  storage_mb             = 32768
  backup_retention_days  = 7
}

resource "azurerm_postgresql_flexible_server_database" "db_staging" {
  name      = "app"
  server_id = azurerm_postgresql_flexible_server.db_staging.id
  charset   = "UTF8"
  collation = "en_US.utf8"
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

resource "azurerm_postgresql_flexible_server" "db_production" {
  name                   = "mon-app-db"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "16"
  administrator_login    = "app"
  administrator_password = random_password.db_production.result
  sku_name               = "B_Standard_B1ms"
  storage_mb             = 32768
  backup_retention_days  = 14
}

resource "azurerm_postgresql_flexible_server_database" "db_production" {
  name      = "app"
  server_id = azurerm_postgresql_flexible_server.db_production.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# --- Azure Key Vault : la pile écrit les secrets (rôle RBAC sur le coffre)
resource "azurerm_role_assignment" "kv_terraform" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# --- Secret mon-app-staging-azure-database (Azure Database (serveur flexible))
resource "azurerm_key_vault_secret" "secret_azure_database_staging" {
  name         = "mon-app-staging-azure-database"
  key_vault_id = azurerm_key_vault.main.id
  content_type = "application/json"
  value        = jsonencode({ url = "postgresql://app:${random_password.db_staging.result}@${azurerm_postgresql_flexible_server.db_staging.fqdn}:5432/app" })

  depends_on = [azurerm_role_assignment.kv_terraform]
}

# --- Secret mon-app-azure-database (Azure Database (serveur flexible))
resource "azurerm_key_vault_secret" "secret_azure_database_production" {
  name         = "mon-app-azure-database"
  key_vault_id = azurerm_key_vault.main.id
  content_type = "application/json"
  value        = jsonencode({ url = "postgresql://app:${random_password.db_production.result}@${azurerm_postgresql_flexible_server.db_production.fqdn}:5432/app" })

  depends_on = [azurerm_role_assignment.kv_terraform]
}

# --- External Secrets : lecture du coffre par le contrôleur (Workload Identity d'AKS)
resource "azurerm_user_assigned_identity" "external_secrets" {
  name                = "id-mon-app-external-secrets"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_role_assignment" "kv_external_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.external_secrets.principal_id
}

resource "azurerm_federated_identity_credential" "external_secrets" {
  name                = "external-secrets"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.external_secrets.id
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:external-secrets:external-secrets"
  audience            = ["api://AzureADTokenExchange"]
}
