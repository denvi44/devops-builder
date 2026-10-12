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

# --- Sauvegardes CloudNativePG (plugin Barman Cloud)
data "google_project" "backups" {
  project_id = var.gcp_project_id
}

resource "google_storage_bucket" "db_backups" {
  name                        = "mon-app-db-backups"
  location                    = "europe-west9"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket_iam_member" "db_backups_mon_app" {
  bucket = google_storage_bucket.db_backups.name
  role   = "roles/storage.objectAdmin"
  member = "principal://iam.googleapis.com/projects/${data.google_project.backups.number}/locations/global/workloadIdentityPools/${var.gcp_project_id}.svc.id.goog/subject/ns/mon-app/sa/mon-app-pg"
}

resource "google_storage_bucket_iam_member" "db_backups_mon_app_staging" {
  bucket = google_storage_bucket.db_backups.name
  role   = "roles/storage.objectAdmin"
  member = "principal://iam.googleapis.com/projects/${data.google_project.backups.number}/locations/global/workloadIdentityPools/${var.gcp_project_id}.svc.id.goog/subject/ns/mon-app-staging/sa/mon-app-pg"
}
