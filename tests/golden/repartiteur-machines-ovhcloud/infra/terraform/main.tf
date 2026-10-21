# Généré par DevOps Builder — à relire avant usage.

provider "ovh" {
  endpoint = "ovh-eu"
}

# --- OVHcloud Private Network
resource "ovh_cloud_project_network_private" "main" {
  service_name = var.ovh_service_name
  name         = "mon-app"
  regions      = ["GRA11"]
  vlan_id      = 10
}

resource "ovh_cloud_project_network_private_subnet" "main" {
  service_name = var.ovh_service_name
  network_id   = ovh_cloud_project_network_private.main.id
  region       = "GRA11"
  network      = "10.30.0.0/24"
  start        = "10.30.0.85"
  end          = "10.30.0.254"
  dhcp         = true
  no_gateway   = false
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

# --- OVHcloud Public Cloud Instances : hors-production (Développement, Recette)
resource "ovh_cloud_project_instance" "hors_production" {
  count          = 1
  service_name   = var.ovh_service_name
  region         = "GRA11"
  billing_period = "hourly"
  name           = "mon-app-hors-production-${count.index + 1}"
  user_data      = local.cloud_init

  flavor {
    flavor_id = [for f in data.ovh_cloud_project_flavors.hosts.flavors : f.id if f.name == "b3-8"][0]
  }

  boot_from {
    image_id = [for image in data.ovh_cloud_project_images.linux.images : image.id if image.name == "Ubuntu 24.04"][0]
  }

  ssh_key_create {
    name       = "mon-app-hors-production-${count.index + 1}"
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

# --- OVHcloud Load Balancer
# --- hors-production : répartiteur
# Les instances ne sont pas encore rattachées au réseau privé : ajouter leurs adresses privées au pool avec
# ovh_cloud_loadbalancer_pool_member (address, protocol_port, subnet_id).
resource "ovh_cloud_loadbalancer" "hors_production" {
  service_name = var.ovh_service_name
  name         = "mon-app-hors-production"
  region       = "GRA11"
  flavor_name  = "SMALL"

  network = {
    id        = tolist(ovh_cloud_project_network_private.main.regions_attributes[*].openstackid)[0]
    subnet_id = ovh_cloud_project_network_private_subnet.main.id
  }
}

resource "ovh_cloud_loadbalancer_pool" "hors_production" {
  service_name    = var.ovh_service_name
  loadbalancer_id = ovh_cloud_loadbalancer.hors_production.id
  name            = "mon-app-hors-production"
  protocol        = "TCP"
  algorithm       = "ROUND_ROBIN"

  health_monitor = {
    type        = "TCP"
    delay       = 5
    timeout     = 3
    max_retries = 3
  }
}

resource "ovh_cloud_loadbalancer_listener" "hors_production_80" {
  service_name    = var.ovh_service_name
  loadbalancer_id = ovh_cloud_loadbalancer.hors_production.id
  name            = "tcp-80"
  protocol        = "TCP"
  protocol_port   = 80
  default_pool_id = ovh_cloud_loadbalancer_pool.hors_production.id
}

resource "ovh_cloud_loadbalancer_listener" "hors_production_443" {
  service_name    = var.ovh_service_name
  loadbalancer_id = ovh_cloud_loadbalancer.hors_production.id
  name            = "tcp-443"
  protocol        = "TCP"
  protocol_port   = 443
  default_pool_id = ovh_cloud_loadbalancer_pool.hors_production.id
}

# --- production : répartiteur
# Les instances ne sont pas encore rattachées au réseau privé : ajouter leurs adresses privées au pool avec
# ovh_cloud_loadbalancer_pool_member (address, protocol_port, subnet_id).
resource "ovh_cloud_loadbalancer" "production" {
  service_name = var.ovh_service_name
  name         = "mon-app-production"
  region       = "GRA11"
  flavor_name  = "SMALL"

  network = {
    id        = tolist(ovh_cloud_project_network_private.main.regions_attributes[*].openstackid)[0]
    subnet_id = ovh_cloud_project_network_private_subnet.main.id
  }
}

resource "ovh_cloud_loadbalancer_pool" "production" {
  service_name    = var.ovh_service_name
  loadbalancer_id = ovh_cloud_loadbalancer.production.id
  name            = "mon-app-production"
  protocol        = "TCP"
  algorithm       = "ROUND_ROBIN"

  health_monitor = {
    type        = "TCP"
    delay       = 5
    timeout     = 3
    max_retries = 3
  }
}

resource "ovh_cloud_loadbalancer_listener" "production_80" {
  service_name    = var.ovh_service_name
  loadbalancer_id = ovh_cloud_loadbalancer.production.id
  name            = "tcp-80"
  protocol        = "TCP"
  protocol_port   = 80
  default_pool_id = ovh_cloud_loadbalancer_pool.production.id
}

resource "ovh_cloud_loadbalancer_listener" "production_443" {
  service_name    = var.ovh_service_name
  loadbalancer_id = ovh_cloud_loadbalancer.production.id
  name            = "tcp-443"
  protocol        = "TCP"
  protocol_port   = 443
  default_pool_id = ovh_cloud_loadbalancer_pool.production.id
}
