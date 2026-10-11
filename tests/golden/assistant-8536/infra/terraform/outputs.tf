# Généré par DevOps Builder — à relire avant usage.

output "cluster_apiserver_url" {
  value = scaleway_k8s_cluster.main.apiserver_url
}

output "registry" {
  value = scaleway_registry_namespace.app.endpoint
}
