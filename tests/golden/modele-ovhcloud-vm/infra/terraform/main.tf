# Généré par DevOps Builder — à relire avant usage.

provider "ovh" {
  endpoint = "ovh-eu"
}

# --- Machines de déploiement (Ubuntu 24.04) : cloud-init pose le compte « deploy », la clé de la CI
# et Docker avec son extension Compose.
locals {
  ssh_cidrs  = ["0.0.0.0/0"]
  cloud_init = <<-EOT
    #cloud-config
    users:
      - name: deploy
        sudo: "ALL=(ALL) NOPASSWD:ALL"
        shell: /bin/bash
        ssh_authorized_keys:
          - ${var.ssh_public_key}
    package_update: true
    packages:
      - docker.io
      - docker-compose-v2
    runcmd:
      - systemctl enable --now docker
      - usermod -aG docker deploy
  EOT
}

# --- OVHcloud Public Cloud Instances : réseau et accès
data "ovh_cloud_project_images" "linux" {
  service_name = var.ovh_service_name
  region       = "GRA11"
  os_type      = "linux"
}

data "ovh_cloud_project_flavors" "hosts" {
  service_name = var.ovh_service_name
  region       = "GRA11"
  name_filter  = "b3-8"
}

# Les instances Public Cloud n'ont pas de pare-feu par défaut : le restreindre (SSH depuis local.ssh_cidrs)
# avec un groupe de sécurité OpenStack ou ufw.

# --- OVHcloud Public Cloud Instances : staging (Préproduction)
resource "ovh_cloud_project_instance" "staging" {
  count          = 1
  service_name   = var.ovh_service_name
  region         = "GRA11"
  billing_period = "hourly"
  name           = "mon-app-staging-${count.index + 1}"
  user_data      = local.cloud_init

  flavor {
    flavor_id = [for f in data.ovh_cloud_project_flavors.hosts.flavors : f.id if f.name == "b3-8"][0]
  }

  boot_from {
    image_id = [for image in data.ovh_cloud_project_images.linux.images : image.id if image.name == "Ubuntu 24.04"][0]
  }

  ssh_key_create {
    name       = "mon-app-staging-${count.index + 1}"
    public_key = var.ssh_public_key
  }

  network {
    public = true
  }
}

# --- OVHcloud Public Cloud Instances : production (Production)
resource "ovh_cloud_project_instance" "production" {
  count          = 1
  service_name   = var.ovh_service_name
  region         = "GRA11"
  billing_period = "hourly"
  name           = "mon-app-production-${count.index + 1}"
  user_data      = local.cloud_init

  flavor {
    flavor_id = [for f in data.ovh_cloud_project_flavors.hosts.flavors : f.id if f.name == "b3-8"][0]
  }

  boot_from {
    image_id = [for image in data.ovh_cloud_project_images.linux.images : image.id if image.name == "Ubuntu 24.04"][0]
  }

  ssh_key_create {
    name       = "mon-app-production-${count.index + 1}"
    public_key = var.ssh_public_key
  }

  network {
    public = true
  }
}
