# Généré par DevOps Builder — à relire avant usage.

provider "ovh" {
  endpoint = "ovh-eu"
}

# --- OVHcloud Managed Kubernetes
resource "ovh_cloud_project_kube" "main" {
  service_name = var.ovh_service_name
  name         = "mon-cluster"
  region       = "GRA11"
}
