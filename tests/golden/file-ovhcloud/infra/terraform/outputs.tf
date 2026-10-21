# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = [for vm in ovh_cloud_project_instance.hors_production : [for a in vm.addresses : a.ip if a.version == 4][0]]
    "production"      = [for vm in ovh_cloud_project_instance.production : [for a in vm.addresses : a.ip if a.version == 4][0]]
  }
}

output "kafka_endpoints" {
  description = "Adresses du cluster Kafka"
  value       = ovh_cloud_project_database.kafka.endpoints
}

output "queue_staging_url" {
  description = "Sujet Kafka"
  value       = ovh_cloud_project_database_kafka_topic.queue_staging.name
}

output "queue_production_url" {
  description = "Sujet Kafka"
  value       = ovh_cloud_project_database_kafka_topic.queue_production.name
}
