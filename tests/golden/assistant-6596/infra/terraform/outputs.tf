# Généré par DevOps Builder — à relire avant usage.

output "cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "registry" {
  value = azurerm_container_registry.main.login_server
}
