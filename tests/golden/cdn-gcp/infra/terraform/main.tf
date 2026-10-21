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

# --- Google Compute Engine : hors-production (Préproduction)
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

# --- Google Cloud Load Balancing
# --- hors-production : répartiteur
resource "google_compute_address" "lb_hors_production" {
  name   = "mon-app-hors-production-lb"
  region = "europe-west9"
}

resource "google_compute_instance_group" "hors_production" {
  name      = "mon-app-hors-production"
  zone      = "europe-west9-a"
  instances = google_compute_instance.hors_production[*].self_link
}

resource "google_compute_region_health_check" "hors_production" {
  name   = "mon-app-hors-production"
  region = "europe-west9"

  tcp_health_check {
    port = 80
  }
}

resource "google_compute_region_backend_service" "hors_production" {
  name                  = "mon-app-hors-production"
  region                = "europe-west9"
  protocol              = "TCP"
  load_balancing_scheme = "EXTERNAL"
  health_checks         = [google_compute_region_health_check.hors_production.id]

  backend {
    group          = google_compute_instance_group.hors_production.id
    balancing_mode = "CONNECTION"
  }
}

resource "google_compute_forwarding_rule" "hors_production" {
  name                  = "mon-app-hors-production"
  region                = "europe-west9"
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL"
  ports                 = ["80", "443"]
  backend_service       = google_compute_region_backend_service.hors_production.id
  ip_address            = google_compute_address.lb_hors_production.address
}

# --- production : répartiteur
resource "google_compute_address" "lb_production" {
  name   = "mon-app-production-lb"
  region = "europe-west9"
}

resource "google_compute_instance_group" "production" {
  name      = "mon-app-production"
  zone      = "europe-west9-a"
  instances = google_compute_instance.production[*].self_link
}

resource "google_compute_region_health_check" "production" {
  name   = "mon-app-production"
  region = "europe-west9"

  tcp_health_check {
    port = 80
  }
}

resource "google_compute_region_backend_service" "production" {
  name                  = "mon-app-production"
  region                = "europe-west9"
  protocol              = "TCP"
  load_balancing_scheme = "EXTERNAL"
  health_checks         = [google_compute_region_health_check.production.id]

  backend {
    group          = google_compute_instance_group.production.id
    balancing_mode = "CONNECTION"
  }
}

resource "google_compute_forwarding_rule" "production" {
  name                  = "mon-app-production"
  region                = "europe-west9"
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL"
  ports                 = ["80", "443"]
  backend_service       = google_compute_region_backend_service.production.id
  ip_address            = google_compute_address.lb_production.address
}

# --- Google Cloud CDN et Cloud Armor
resource "google_compute_global_network_endpoint_group" "cdn" {
  name                  = "mon-app-cdn-origin"
  network_endpoint_type = "INTERNET_IP_PORT"
  default_port          = 443
}

resource "google_compute_global_network_endpoint" "cdn" {
  global_network_endpoint_group = google_compute_global_network_endpoint_group.cdn.id
  ip_address                    = google_compute_address.lb_production.address
  port                          = 443
}

resource "google_compute_security_policy" "cdn" {
  name = "mon-app-cdn"

  rule {
    action      = "deny(403)"
    priority    = 1000
    description = "Injections SQL"

    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable')"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1001
    description = "Scripts intersites"

    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable')"
      }
    }
  }

  rule {
    action      = "throttle"
    priority    = 2000
    description = "Limite par adresse"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }

    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"

      rate_limit_threshold {
        count        = 2000
        interval_sec = 60
      }
    }
  }

  rule {
    action      = "allow"
    priority    = 2147483647
    description = "Règle par défaut"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}

resource "google_compute_backend_service" "cdn" {
  name                  = "mon-app-cdn"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  enable_cdn            = true
  security_policy       = google_compute_security_policy.cdn.id

  backend {
    group = google_compute_global_network_endpoint_group.cdn.id
  }

  cdn_policy {
    cache_mode = "USE_ORIGIN_HEADERS"
  }

  depends_on = [google_compute_global_network_endpoint.cdn]
}

resource "google_compute_url_map" "cdn" {
  name            = "mon-app-cdn"
  default_service = google_compute_backend_service.cdn.id
}

resource "google_compute_target_http_proxy" "cdn" {
  name    = "mon-app-cdn-http"
  url_map = google_compute_url_map.cdn.id
}

resource "google_compute_global_address" "cdn" {
  name = "mon-app-cdn"
}

resource "google_compute_global_forwarding_rule" "cdn_http" {
  name                  = "mon-app-cdn-http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.cdn.id
  port_range            = "80"
  target                = google_compute_target_http_proxy.cdn.id
}
