# Généré par DevOps Builder — à relire avant usage.

output "registry" {
  value = google_artifact_registry_repository.app.id
}

output "fn_staging_url" {
  description = "Adresse HTTPS de la fonction"
  value       = google_cloudfunctions2_function.fn_staging.service_config[0].uri
}

output "fn_production_url" {
  description = "Adresse HTTPS de la fonction"
  value       = google_cloudfunctions2_function.fn_production.service_config[0].uri
}
