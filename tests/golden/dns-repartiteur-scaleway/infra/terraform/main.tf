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

# --- Scaleway Instances : hors-production (Développement, Recette)
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

# --- Scaleway Load Balancer
# --- hors-production : répartiteur
resource "scaleway_lb_ip" "hors_production" {
}

resource "scaleway_lb" "hors_production" {
  name   = "mon-app-hors-production"
  type   = "LB-S"
  ip_ids = [scaleway_lb_ip.hors_production.id]
}

resource "scaleway_lb_backend" "hors_production_80" {
  lb_id            = scaleway_lb.hors_production.id
  name             = "tcp-80"
  forward_protocol = "tcp"
  forward_port     = 80
  server_ips       = scaleway_instance_ip.hors_production[*].address

  health_check_tcp {}
}

resource "scaleway_lb_frontend" "hors_production_80" {
  lb_id        = scaleway_lb.hors_production.id
  backend_id   = scaleway_lb_backend.hors_production_80.id
  name         = "tcp-80"
  inbound_port = 80
}

resource "scaleway_lb_backend" "hors_production_443" {
  lb_id            = scaleway_lb.hors_production.id
  name             = "tcp-443"
  forward_protocol = "tcp"
  forward_port     = 443
  server_ips       = scaleway_instance_ip.hors_production[*].address

  health_check_tcp {}
}

resource "scaleway_lb_frontend" "hors_production_443" {
  lb_id        = scaleway_lb.hors_production.id
  backend_id   = scaleway_lb_backend.hors_production_443.id
  name         = "tcp-443"
  inbound_port = 443
}

# --- production : répartiteur
resource "scaleway_lb_ip" "production" {
}

resource "scaleway_lb" "production" {
  name   = "mon-app-production"
  type   = "LB-S"
  ip_ids = [scaleway_lb_ip.production.id]
}

resource "scaleway_lb_backend" "production_80" {
  lb_id            = scaleway_lb.production.id
  name             = "tcp-80"
  forward_protocol = "tcp"
  forward_port     = 80
  server_ips       = scaleway_instance_ip.production[*].address

  health_check_tcp {}
}

resource "scaleway_lb_frontend" "production_80" {
  lb_id        = scaleway_lb.production.id
  backend_id   = scaleway_lb_backend.production_80.id
  name         = "tcp-80"
  inbound_port = 80
}

resource "scaleway_lb_backend" "production_443" {
  lb_id            = scaleway_lb.production.id
  name             = "tcp-443"
  forward_protocol = "tcp"
  forward_port     = 443
  server_ips       = scaleway_instance_ip.production[*].address

  health_check_tcp {}
}

resource "scaleway_lb_frontend" "production_443" {
  lb_id        = scaleway_lb.production.id
  backend_id   = scaleway_lb_backend.production_443.id
  name         = "tcp-443"
  inbound_port = 443
}

# --- Scaleway Domains and DNS
resource "scaleway_domain_record" "hors_production" {
  dns_zone = "boutique.fr"
  name     = "boutique-hors-production"
  type     = "A"
  data     = scaleway_lb_ip.hors_production.ip_address
  ttl      = 300
}

resource "scaleway_domain_record" "production" {
  dns_zone = "boutique.fr"
  name     = "boutique"
  type     = "A"
  data     = scaleway_lb_ip.production.ip_address
  ttl      = 300
}
