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

# --- Scaleway Messaging and Queuing (SQS)
resource "scaleway_mnq_sqs" "main" {
}

resource "scaleway_mnq_sqs_credentials" "queue_staging" {
  project_id = scaleway_mnq_sqs.main.project_id
  name       = "mon-app-staging-app"

  permissions {
    can_publish = true
    can_receive = true
    can_manage  = false
  }
}

resource "scaleway_mnq_sqs_queue" "queue_staging" {
  project_id      = scaleway_mnq_sqs.main.project_id
  name            = "mon-app-staging"
  sqs_endpoint    = scaleway_mnq_sqs.main.endpoint
  access_key      = scaleway_mnq_sqs_credentials.queue_staging.access_key
  secret_key      = scaleway_mnq_sqs_credentials.queue_staging.secret_key
  message_max_age = 345600
}

resource "scaleway_mnq_sqs_credentials" "queue_production" {
  project_id = scaleway_mnq_sqs.main.project_id
  name       = "mon-app-app"

  permissions {
    can_publish = true
    can_receive = true
    can_manage  = false
  }
}

resource "scaleway_mnq_sqs_queue" "queue_production" {
  project_id      = scaleway_mnq_sqs.main.project_id
  name            = "mon-app"
  sqs_endpoint    = scaleway_mnq_sqs.main.endpoint
  access_key      = scaleway_mnq_sqs_credentials.queue_production.access_key
  secret_key      = scaleway_mnq_sqs_credentials.queue_production.secret_key
  message_max_age = 345600
}
