# Généré par DevOps Builder — à relire avant usage.

provider "scaleway" {
  region = "fr-par"
  zone   = "fr-par-1"
}

# --- Scaleway Container Registry
resource "scaleway_registry_namespace" "app" {
  name = "mon-app"
}

# --- Scaleway Kapsule
data "scaleway_k8s_version" "latest" {
  name = "latest"
}

resource "scaleway_k8s_cluster" "main" {
  name                        = "mon-cluster"
  version                     = data.scaleway_k8s_version.latest.name
  cni                         = "cilium"
  delete_additional_resources = false
}

resource "scaleway_k8s_pool" "default" {
  cluster_id = scaleway_k8s_cluster.main.id
  name       = "default"
  node_type  = "DEV1-M"
  size       = 2
}
