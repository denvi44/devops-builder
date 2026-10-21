# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = aws_instance.hors_production[*].public_ip
    "production"      = aws_instance.production[*].public_ip
  }
}

output "queue_staging_url" {
  description = "Adresse de la file SQS"
  value       = aws_sqs_queue.queue_staging.url
}

output "queue_production_url" {
  description = "Adresse de la file SQS"
  value       = aws_sqs_queue.queue_production.url
}
