# Généré par DevOps Builder — à relire avant usage.

output "cluster_name" {
  value = google_container_cluster.main.name
}

output "registry" {
  value = google_artifact_registry_repository.app.id
}

output "db_staging_connection_name" {
  description = "Pour le Cloud SQL Auth Proxy"
  value       = google_sql_database_instance.db_staging.connection_name
}

output "db_staging_password" {
  value     = random_password.db_staging.result
  sensitive = true
}

output "db_production_connection_name" {
  description = "Pour le Cloud SQL Auth Proxy"
  value       = google_sql_database_instance.db_production.connection_name
}

output "db_production_password" {
  value     = random_password.db_production.result
  sensitive = true
}
