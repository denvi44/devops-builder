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
