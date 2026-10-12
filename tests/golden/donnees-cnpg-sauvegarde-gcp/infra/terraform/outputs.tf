# Généré par DevOps Builder — à relire avant usage.

output "cluster_name" {
  value = google_container_cluster.main.name
}

output "registry" {
  value = google_artifact_registry_repository.app.id
}

output "db_backups_bucket" {
  value = google_storage_bucket.db_backups.name
}
