# Généré par DevOps Builder — à relire avant usage.

provider "google" {
  project = var.gcp_project_id
  region  = "europe-west9"
}

# --- Google Cloud Storage
# Le bucket mon-projet-tfstate porte l'état de cette pile : il est créé à part (amorçage),
# pas par la pile qui l'utilise.

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

# --- Google Compute Engine : réseau et accès
resource "google_compute_firewall" "ssh" {
  name          = "mon-app-ssh"
  network       = "default"
  source_ranges = local.ssh_cidrs
  target_tags   = ["mon-app"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "google_compute_firewall" "web" {
  name          = "mon-app-web"
  network       = "default"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["mon-app"]

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
}

# --- Google Compute Engine : hors-production (Développement, Recette)
resource "google_compute_instance" "hors_production" {
  count        = 1
  name         = "mon-app-hors-production-${count.index + 1}"
  machine_type = "e2-small"
  zone         = "europe-west9-a"
  tags         = ["mon-app"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = 30
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata = {
    user-data = local.cloud_init
  }

  shielded_instance_config {
    enable_secure_boot = true
  }
}

# --- Google Compute Engine : production (Production)
resource "google_compute_instance" "production" {
  count        = 1
  name         = "mon-app-production-${count.index + 1}"
  machine_type = "e2-small"
  zone         = "europe-west9-a"
  tags         = ["mon-app"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = 30
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata = {
    user-data = local.cloud_init
  }

  shielded_instance_config {
    enable_secure_boot = true
  }
}
