# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = scaleway_instance_ip.hors_production[*].address
    "production"      = scaleway_instance_ip.production[*].address
  }
}

output "queue_staging_url" {
  description = "Adresse de la file"
  value       = scaleway_mnq_sqs_queue.queue_staging.url
}

output "queue_staging_access_key" {
  description = "Identifiant d'accès de l'application"
  value       = scaleway_mnq_sqs_credentials.queue_staging.access_key
}

output "queue_staging_secret_key" {
  description = "Clé secrète de l'application"
  value       = scaleway_mnq_sqs_credentials.queue_staging.secret_key
  sensitive   = true
}

output "queue_production_url" {
  description = "Adresse de la file"
  value       = scaleway_mnq_sqs_queue.queue_production.url
}

output "queue_production_access_key" {
  description = "Identifiant d'accès de l'application"
  value       = scaleway_mnq_sqs_credentials.queue_production.access_key
}

output "queue_production_secret_key" {
  description = "Clé secrète de l'application"
  value       = scaleway_mnq_sqs_credentials.queue_production.secret_key
  sensitive   = true
}
