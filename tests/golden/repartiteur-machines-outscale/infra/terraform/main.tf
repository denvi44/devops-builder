# Généré par DevOps Builder — à relire avant usage.

provider "outscale" {
  region = "eu-west-2"
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

# --- Outscale VM : réseau et accès
data "outscale_images" "ubuntu" {
  filter {
    name   = "account_aliases"
    values = ["Outscale"]
  }

  filter {
    name   = "image_names"
    values = ["Ubuntu-24.04-*"]
  }
}

resource "outscale_keypair" "deploy" {
  keypair_name = "mon-app-deploy"
  public_key   = var.ssh_public_key
}

resource "outscale_security_group" "hosts" {
  security_group_name = "mon-app-hosts"
  description         = "SSH depuis local.ssh_cidrs, web depuis Internet"
}

resource "outscale_security_group_rule" "ssh" {
  flow              = "Inbound"
  security_group_id = outscale_security_group.hosts.security_group_id

  rules {
    from_port_range = 22
    to_port_range   = 22
    ip_protocol     = "tcp"
    ip_ranges       = local.ssh_cidrs
  }
}

resource "outscale_security_group_rule" "web" {
  flow              = "Inbound"
  security_group_id = outscale_security_group.hosts.security_group_id

  rules {
    from_port_range = 80
    to_port_range   = 80
    ip_protocol     = "tcp"
    ip_ranges       = ["0.0.0.0/0"]
  }

  rules {
    from_port_range = 443
    to_port_range   = 443
    ip_protocol     = "tcp"
    ip_ranges       = ["0.0.0.0/0"]
  }
}

# --- Outscale VM : hors-production (Développement, Recette)
resource "outscale_vm" "hors_production" {
  count                    = 1
  image_id                 = data.outscale_images.ubuntu.images[0].image_id
  vm_type                  = "tinav6.c2r4p2"
  keypair_name             = outscale_keypair.deploy.keypair_name
  security_group_ids       = [outscale_security_group.hosts.security_group_id]
  placement_subregion_name = "eu-west-2a"
  user_data                = base64encode(local.cloud_init)

  block_device_mappings {
    device_name = "/dev/sda1"
    bsu {
      volume_size = 30
      volume_type = "gp2"
    }
  }

  tags {
    key   = "name"
    value = "mon-app-hors-production-${count.index + 1}"
  }
}

resource "outscale_public_ip" "hors_production" {
  count = 1
}

resource "outscale_public_ip_link" "hors_production" {
  count     = 1
  vm_id     = outscale_vm.hors_production[count.index].vm_id
  public_ip = outscale_public_ip.hors_production[count.index].public_ip
}

# --- Outscale VM : production (Production)
resource "outscale_vm" "production" {
  count                    = 1
  image_id                 = data.outscale_images.ubuntu.images[0].image_id
  vm_type                  = "tinav6.c2r4p2"
  keypair_name             = outscale_keypair.deploy.keypair_name
  security_group_ids       = [outscale_security_group.hosts.security_group_id]
  placement_subregion_name = "eu-west-2a"
  user_data                = base64encode(local.cloud_init)

  block_device_mappings {
    device_name = "/dev/sda1"
    bsu {
      volume_size = 30
      volume_type = "gp2"
    }
  }

  tags {
    key   = "name"
    value = "mon-app-production-${count.index + 1}"
  }
}

resource "outscale_public_ip" "production" {
  count = 1
}

resource "outscale_public_ip_link" "production" {
  count     = 1
  vm_id     = outscale_vm.production[count.index].vm_id
  public_ip = outscale_public_ip.production[count.index].public_ip
}

# --- Outscale Load Balancer Unit
# --- hors-production : répartiteur
resource "outscale_load_balancer" "hors_production" {
  load_balancer_name = "mon-app-hors-production"
  subregion_names    = ["eu-west-2a"]

  listeners {
    backend_port           = 80
    backend_protocol       = "TCP"
    load_balancer_port     = 80
    load_balancer_protocol = "TCP"
  }

  listeners {
    backend_port           = 443
    backend_protocol       = "TCP"
    load_balancer_port     = 443
    load_balancer_protocol = "TCP"
  }

}

resource "outscale_load_balancer_attributes" "hors_production" {
  load_balancer_name = outscale_load_balancer.hors_production.load_balancer_name

  health_check {
    healthy_threshold   = 3
    unhealthy_threshold = 3
    check_interval      = 30
    timeout             = 5
    protocol            = "TCP"
    port                = 80
  }
}

resource "outscale_load_balancer_vms" "hors_production" {
  load_balancer_name = outscale_load_balancer.hors_production.load_balancer_name
  backend_vm_ids     = outscale_vm.hors_production[*].vm_id
}

# --- production : répartiteur
resource "outscale_load_balancer" "production" {
  load_balancer_name = "mon-app-production"
  subregion_names    = ["eu-west-2a"]

  listeners {
    backend_port           = 80
    backend_protocol       = "TCP"
    load_balancer_port     = 80
    load_balancer_protocol = "TCP"
  }

  listeners {
    backend_port           = 443
    backend_protocol       = "TCP"
    load_balancer_port     = 443
    load_balancer_protocol = "TCP"
  }

}

resource "outscale_load_balancer_attributes" "production" {
  load_balancer_name = outscale_load_balancer.production.load_balancer_name

  health_check {
    healthy_threshold   = 3
    unhealthy_threshold = 3
    check_interval      = 30
    timeout             = 5
    protocol            = "TCP"
    port                = 80
  }
}

resource "outscale_load_balancer_vms" "production" {
  load_balancer_name = outscale_load_balancer.production.load_balancer_name
  backend_vm_ids     = outscale_vm.production[*].vm_id
}
