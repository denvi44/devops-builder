# Généré par DevOps Builder — à relire avant usage.

output "cluster_id" {
  value = ovh_cloud_project_kube.main.id
}

output "private_network_id" {
  value = ovh_cloud_project_network_private.main.id
}

output "db_staging_endpoints" {
  value = ovh_cloud_project_database.db_staging.endpoints
}

output "db_staging_password" {
  value     = ovh_cloud_project_database_postgresql_user.db_staging.password
  sensitive = true
}

output "db_production_endpoints" {
  value = ovh_cloud_project_database.db_production.endpoints
}

output "db_production_password" {
  value     = ovh_cloud_project_database_postgresql_user.db_production.password
  sensitive = true
}
