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

  network    = google_compute_network.main.id
  subnetwork = google_compute_subnetwork.main.id

  ip_allocation_policy {}
}

# --- Google Cloud Storage
# Le bucket mon-projet-tfstate porte l'état de cette pile : il est créé à part (amorçage),
# pas par la pile qui l'utilise.

# --- Google Cloud VPC
resource "google_compute_network" "main" {
  name                    = "mon-app"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name                     = "mon-app"
  region                   = "europe-west9"
  network                  = google_compute_network.main.id
  ip_cidr_range            = "10.10.0.0/16"
  private_ip_google_access = true
}

# Cloud SQL en adresse privée : accès aux services Google par appairage du réseau (l'API Service Networking
# doit être activée dans le projet).
resource "google_compute_global_address" "private_services" {
  name          = "mon-app-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

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

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }

  depends_on = [google_service_networking_connection.private_services]
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

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }

  depends_on = [google_service_networking_connection.private_services]
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
