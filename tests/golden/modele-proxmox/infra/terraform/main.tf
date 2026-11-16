# Généré par DevOps Builder — à relire avant usage.

provider "proxmox" {
  endpoint = "https://pve.example.lan:8006/"
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

# --- Proxmox VE (machines virtuelles) : réseau et accès
# Modèle à cloner : VM n° 9000 du nœud « pve »
# (Ubuntu 24.04 cloud-init, qemu-guest-agent installé), à préparer une fois à la main.
# Docker est posé par ansible/site.yml, ou déjà présent dans le modèle.

# --- Proxmox VE (machines virtuelles) : staging (Préproduction)
resource "proxmox_virtual_environment_vm" "staging" {
  count     = 1
  name      = "mon-app-staging-${count.index + 1}"
  node_name = "pve"
  tags      = ["mon-app"]

  clone {
    vm_id = 9000
  }

  agent {
    enabled = true
  }

  cpu {
    cores = 2
  }

  memory {
    dedicated = 4096
  }

  disk {
    datastore_id = "local-lvm"
    interface    = "scsi0"
    size         = 30
  }

  network_device {
    bridge = "vmbr0"
  }

  initialization {
    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }
    user_account {
      username = "deploy"
      keys     = [var.ssh_public_key]
    }
  }
}

# --- Proxmox VE (machines virtuelles) : production (Production)
resource "proxmox_virtual_environment_vm" "production" {
  count     = 1
  name      = "mon-app-production-${count.index + 1}"
  node_name = "pve"
  tags      = ["mon-app"]

  clone {
    vm_id = 9000
  }

  agent {
    enabled = true
  }

  cpu {
    cores = 2
  }

  memory {
    dedicated = 4096
  }

  disk {
    datastore_id = "local-lvm"
    interface    = "scsi0"
    size         = 30
  }

  network_device {
    bridge = "vmbr0"
  }

  initialization {
    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }
    user_account {
      username = "deploy"
      keys     = [var.ssh_public_key]
    }
  }
}
