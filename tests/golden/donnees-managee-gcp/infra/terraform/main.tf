# Généré par DevOps Builder — à relire avant usage.

provider "google" {
  project = var.gcp_project_id
  region  = "europe-west9"
}

# --- Google Artifact Registry
resource "google_artifact_registry_repository" "app" {
  location      = "europe-west9"
  repository_id = "mon-app"
  format        = "DOCKER"
}

# --- Google Kubernetes Engine
resource "google_container_cluster" "main" {
  name     = "mon-cluster"
  location = "europe-west9"

  enable_autopilot    = true
  deletion_protection = true
}

# --- Google Cloud Storage
# Le bucket mon-projet-tfstate porte l'état de cette pile : il est créé à part (amorçage),
# pas par la pile qui l'utilise.

# --- Google Cloud SQL (Préproduction)
resource "google_sql_database_instance" "db_staging" {
  name                = "mon-app-staging"
  database_version    = "POSTGRES_17"
  region              = "europe-west9"
  deletion_protection = false

  settings {
    edition           = "ENTERPRISE"
    tier              = "db-custom-1-3840"
    availability_type = "ZONAL"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }
}

resource "google_sql_database" "db_staging" {
  name     = "app"
  instance = google_sql_database_instance.db_staging.name
}

resource "random_password" "db_staging" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "google_sql_user" "db_staging" {
  name     = "app"
  instance = google_sql_database_instance.db_staging.name
  password = random_password.db_staging.result
}

# --- Google Cloud SQL (Production)
resource "google_sql_database_instance" "db_production" {
  name                = "mon-app"
  database_version    = "POSTGRES_17"
  region              = "europe-west9"
  deletion_protection = true

  settings {
    edition           = "ENTERPRISE"
    tier              = "db-custom-1-3840"
    availability_type = "REGIONAL"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }
}

resource "google_sql_database" "db_production" {
  name     = "app"
  instance = google_sql_database_instance.db_production.name
}

resource "random_password" "db_production" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "google_sql_user" "db_production" {
  name     = "app"
  instance = google_sql_database_instance.db_production.name
  password = random_password.db_production.result
}
