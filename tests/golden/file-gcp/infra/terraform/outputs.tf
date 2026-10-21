# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = [for vm in google_compute_instance.hors_production : vm.network_interface[0].access_config[0].nat_ip]
    "production"      = [for vm in google_compute_instance.production : vm.network_interface[0].access_config[0].nat_ip]
  }
}

output "queue_staging_url" {
  description = "Sujet Pub/Sub (projects/<projet>/topics/<nom>)"
  value       = google_pubsub_topic.queue_staging.id
}

output "queue_staging_subscription" {
  description = "Abonnement Pub/Sub"
  value       = google_pubsub_subscription.queue_staging.id
}

output "queue_production_url" {
  description = "Sujet Pub/Sub (projects/<projet>/topics/<nom>)"
  value       = google_pubsub_topic.queue_production.id
}

output "queue_production_subscription" {
  description = "Abonnement Pub/Sub"
  value       = google_pubsub_subscription.queue_production.id
}
