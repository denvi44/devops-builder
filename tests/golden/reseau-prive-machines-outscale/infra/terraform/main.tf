# Généré par DevOps Builder — à relire avant usage.

provider "outscale" {
  region = "eu-west-2"
}

# --- Outscale Net
resource "outscale_net" "main" {
  ip_range = "10.40.0.0/16"

  tags {
    key   = "name"
    value = "mon-app"
  }
}

resource "outscale_subnet" "main" {
  net_id         = outscale_net.main.net_id
  ip_range       = "10.40.0.0/24"
  subregion_name = "eu-west-2a"
}

# Sortie vers Internet : service Internet du Net, route par défaut de la table associée au sous-réseau.
resource "outscale_internet_service" "main" {
}

resource "outscale_internet_service_link" "main" {
  internet_service_id = outscale_internet_service.main.internet_service_id
  net_id              = outscale_net.main.net_id
}

resource "outscale_route_table" "main" {
  net_id = outscale_net.main.net_id
}

resource "outscale_route" "internet" {
  route_table_id       = outscale_route_table.main.route_table_id
  gateway_id           = outscale_internet_service.main.internet_service_id
  destination_ip_range = "0.0.0.0/0"

  depends_on = [outscale_internet_service_link.main]
}

resource "outscale_route_table_link" "main" {
  subnet_id      = outscale_subnet.main.subnet_id
  route_table_id = outscale_route_table.main.route_table_id
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
  net_id              = outscale_net.main.net_id
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
  count              = 1
  image_id           = data.outscale_images.ubuntu.images[0].image_id
  vm_type            = "tinav6.c2r4p2"
  keypair_name       = outscale_keypair.deploy.keypair_name
  security_group_ids = [outscale_security_group.hosts.security_group_id]
  subnet_id          = outscale_subnet.main.subnet_id
  user_data          = base64encode(local.cloud_init)

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

  depends_on = [outscale_route.internet]
}

# --- Outscale VM : production (Production)
resource "outscale_vm" "production" {
  count              = 1
  image_id           = data.outscale_images.ubuntu.images[0].image_id
  vm_type            = "tinav6.c2r4p2"
  keypair_name       = outscale_keypair.deploy.keypair_name
  security_group_ids = [outscale_security_group.hosts.security_group_id]
  subnet_id          = outscale_subnet.main.subnet_id
  user_data          = base64encode(local.cloud_init)

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

  depends_on = [outscale_route.internet]
}
