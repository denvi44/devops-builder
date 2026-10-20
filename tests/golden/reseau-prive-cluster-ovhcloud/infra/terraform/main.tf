# Généré par DevOps Builder — à relire avant usage.

provider "ovh" {
  endpoint = "ovh-eu"
}

# --- OVHcloud Managed Kubernetes
resource "ovh_cloud_project_kube" "main" {
  service_name       = var.ovh_service_name
  name               = "mon-cluster"
  region             = "GRA11"
  private_network_id = tolist(ovh_cloud_project_network_private.main.regions_attributes[*].openstackid)[0]
  nodes_subnet_id    = ovh_cloud_project_network_private_subnet.main.id

  depends_on = [ovh_cloud_project_network_private_subnet.main]
}

# --- OVHcloud Private Network
resource "ovh_cloud_project_network_private" "main" {
  service_name = var.ovh_service_name
  name         = "mon-app"
  regions      = ["GRA11"]
  vlan_id      = 10
}

resource "ovh_cloud_project_network_private_subnet" "main" {
  service_name = var.ovh_service_name
  network_id   = ovh_cloud_project_network_private.main.id
  region       = "GRA11"
  network      = "10.30.0.0/24"
  start        = "10.30.0.85"
  end          = "10.30.0.254"
  dhcp         = true
  no_gateway   = false
}

# --- OVHcloud Public Cloud Databases (Préproduction)
resource "ovh_cloud_project_database" "db_staging" {
  service_name = var.ovh_service_name
  description  = "mon-app-staging"
  engine       = "postgresql"
  version      = "16"
  plan         = "essential"
  flavor       = "db1-4"

  # Offres à plusieurs nœuds (business, enterprise…) : un bloc nodes par nœud.
  nodes {
    region = "GRA"
  }
}

resource "ovh_cloud_project_database_database" "db_staging" {
  service_name = ovh_cloud_project_database.db_staging.service_name
  engine       = ovh_cloud_project_database.db_staging.engine
  cluster_id   = ovh_cloud_project_database.db_staging.id
  name         = "app"
}

resource "ovh_cloud_project_database_postgresql_user" "db_staging" {
  service_name = ovh_cloud_project_database.db_staging.service_name
  cluster_id   = ovh_cloud_project_database.db_staging.id
  name         = "app"
}

# --- OVHcloud Public Cloud Databases (Production)
resource "ovh_cloud_project_database" "db_production" {
  service_name = var.ovh_service_name
  description  = "mon-app"
  engine       = "postgresql"
  version      = "16"
  plan         = "essential"
  flavor       = "db1-4"

  # Offres à plusieurs nœuds (business, enterprise…) : un bloc nodes par nœud.
  nodes {
    region = "GRA"
  }
}

resource "ovh_cloud_project_database_database" "db_production" {
  service_name = ovh_cloud_project_database.db_production.service_name
  engine       = ovh_cloud_project_database.db_production.engine
  cluster_id   = ovh_cloud_project_database.db_production.id
  name         = "app"
}

resource "ovh_cloud_project_database_postgresql_user" "db_production" {
  service_name = ovh_cloud_project_database.db_production.service_name
  cluster_id   = ovh_cloud_project_database.db_production.id
  name         = "app"
}
