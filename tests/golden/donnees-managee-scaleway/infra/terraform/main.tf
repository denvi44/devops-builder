# Généré par DevOps Builder — à relire avant usage.

provider "scaleway" {
  region = "fr-par"
  zone   = "fr-par-1"
}

# --- Scaleway Container Registry
resource "scaleway_registry_namespace" "app" {
  name = "mon-app"
}

# --- Scaleway Kapsule
resource "scaleway_k8s_cluster" "main" {
  name                        = "mon-cluster"
  version                     = "1.32"
  cni                         = "cilium"
  delete_additional_resources = false
}

resource "scaleway_k8s_pool" "default" {
  cluster_id = scaleway_k8s_cluster.main.id
  name       = "default"
  node_type  = "DEV1-M"
  size       = 2
}

# --- Scaleway Managed Database (Préproduction)
resource "random_password" "db_staging" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "scaleway_rdb_instance" "db_staging" {
  name                      = "mon-app-staging"
  node_type                 = "DB-DEV-S"
  engine                    = "PostgreSQL-16"
  is_ha_cluster             = false
  disable_backup            = false
  backup_schedule_frequency = 24
  backup_schedule_retention = 7
  encryption_at_rest        = true
  user_name                 = "app"
  password                  = random_password.db_staging.result
}

resource "scaleway_rdb_database" "db_staging" {
  instance_id = scaleway_rdb_instance.db_staging.id
  name        = "app"
}

# --- Scaleway Managed Database (Production)
resource "random_password" "db_production" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "scaleway_rdb_instance" "db_production" {
  name                      = "mon-app"
  node_type                 = "DB-DEV-S"
  engine                    = "PostgreSQL-16"
  is_ha_cluster             = true
  disable_backup            = false
  backup_schedule_frequency = 24
  backup_schedule_retention = 14
  encryption_at_rest        = true
  user_name                 = "app"
  password                  = random_password.db_production.result
}

resource "scaleway_rdb_database" "db_production" {
  instance_id = scaleway_rdb_instance.db_production.id
  name        = "app"
}
