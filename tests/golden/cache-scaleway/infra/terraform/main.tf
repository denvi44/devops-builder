# Généré par DevOps Builder — à relire avant usage.

provider "scaleway" {
  region = "fr-par"
  zone   = "fr-par-1"
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

# --- Scaleway Instances : réseau et accès
resource "scaleway_iam_ssh_key" "deploy" {
  name       = "mon-app-deploy"
  public_key = var.ssh_public_key
}

resource "scaleway_instance_security_group" "hosts" {
  name                    = "mon-app-hosts"
  inbound_default_policy  = "drop"
  outbound_default_policy = "accept"

  dynamic "inbound_rule" {
    for_each = local.ssh_cidrs
    content {
      action   = "accept"
      port     = 22
      ip_range = inbound_rule.value
    }
  }

  inbound_rule {
    action = "accept"
    port   = 80
  }

  inbound_rule {
    action = "accept"
    port   = 443
  }
}

# --- Scaleway Instances : hors-production (Préproduction)
resource "scaleway_instance_ip" "hors_production" {
  count = 1
}

resource "scaleway_instance_server" "hors_production" {
  count             = 1
  name              = "mon-app-hors-production-${count.index + 1}"
  type              = "PLAY2-NANO"
  image             = "ubuntu_noble"
  ip_id             = scaleway_instance_ip.hors_production[count.index].id
  security_group_id = scaleway_instance_security_group.hosts.id
  user_data = {
    cloud-init = local.cloud_init
  }

  root_volume {
    size_in_gb = 30
  }

  depends_on = [scaleway_iam_ssh_key.deploy]
}

# --- Scaleway Instances : production (Production)
resource "scaleway_instance_ip" "production" {
  count = 1
}

resource "scaleway_instance_server" "production" {
  count             = 1
  name              = "mon-app-production-${count.index + 1}"
  type              = "PLAY2-NANO"
  image             = "ubuntu_noble"
  ip_id             = scaleway_instance_ip.production[count.index].id
  security_group_id = scaleway_instance_security_group.hosts.id
  user_data = {
    cloud-init = local.cloud_init
  }

  root_volume {
    size_in_gb = 30
  }

  depends_on = [scaleway_iam_ssh_key.deploy]
}

# --- Scaleway Managed Database for Redis (Préproduction)
resource "random_password" "cache_scaleway_staging" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "scaleway_redis_cluster" "cache_scaleway_staging" {
  name         = "mon-app-staging"
  version      = "7.2.11"
  node_type    = "RED1-MICRO"
  user_name    = "default"
  password     = random_password.cache_scaleway_staging.result
  cluster_size = 1
  tls_enabled  = true
}

# --- Scaleway Managed Database for Redis (Production)
resource "random_password" "cache_scaleway_production" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "scaleway_redis_cluster" "cache_scaleway_production" {
  name         = "mon-app"
  version      = "7.2.11"
  node_type    = "RED1-MICRO"
  user_name    = "default"
  password     = random_password.cache_scaleway_production.result
  cluster_size = 2
  tls_enabled  = true
}
