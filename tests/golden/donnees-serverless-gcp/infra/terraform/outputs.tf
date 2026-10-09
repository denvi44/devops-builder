# Généré par DevOps Builder — à relire avant usage.

output "db_connection_name" {
  description = "Pour le Cloud SQL Auth Proxy"
  value       = google_sql_database_instance.db.connection_name
}

output "db_password" {
  value     = random_password.db.result
  sensitive = true
}
