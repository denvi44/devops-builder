# Généré par DevOps Builder — à relire avant usage.

output "cluster_apiserver_url" {
  value = scaleway_k8s_cluster.main.apiserver_url
}

output "registry" {
  value = scaleway_registry_namespace.app.endpoint
}

output "db_staging_endpoint" {
  value = scaleway_rdb_instance.db_staging.load_balancer
}

output "db_staging_password" {
  value     = random_password.db_staging.result
  sensitive = true
}

output "db_production_endpoint" {
  value = scaleway_rdb_instance.db_production.load_balancer
}

output "db_production_password" {
  value     = random_password.db_production.result
  sensitive = true
}
