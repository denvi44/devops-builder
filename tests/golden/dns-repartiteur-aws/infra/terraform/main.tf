# Généré par DevOps Builder — à relire avant usage.

provider "aws" {
  region = "eu-west-3"
}

# --- Amazon S3
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

# --- Amazon EC2 : réseau et accès
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

resource "aws_key_pair" "deploy" {
  key_name   = "mon-app-deploy"
  public_key = var.ssh_public_key
}

resource "aws_security_group" "hosts" {
  name        = "mon-app-hosts"
  description = "SSH depuis local.ssh_cidrs, web depuis Internet"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = local.ssh_cidrs
  }

  ingress {
    description = "Port 80"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Port 443"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Amazon EC2 : hors-production (Développement, Recette)
resource "aws_instance" "hors_production" {
  count                  = 1
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.small"
  key_name               = aws_key_pair.deploy.key_name
  vpc_security_group_ids = [aws_security_group.hosts.id]
  user_data              = local.cloud_init

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name                   = "mon-app-hors-production-${count.index + 1}"
    "devops-builder:hosts" = "hors-production"
  }
}

# --- Amazon EC2 : production (Production)
resource "aws_instance" "production" {
  count                  = 1
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.small"
  key_name               = aws_key_pair.deploy.key_name
  vpc_security_group_ids = [aws_security_group.hosts.id]
  user_data              = local.cloud_init

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name                   = "mon-app-production-${count.index + 1}"
    "devops-builder:hosts" = "production"
  }
}

# --- Amazon Elastic Load Balancing (NLB)
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# --- hors-production : répartiteur
resource "aws_lb" "hors_production" {
  name               = "mon-app-hors-production"
  load_balancer_type = "network"
  internal           = false
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "hors_production_80" {
  name        = "mon-app-hors-production-80"
  port        = 80
  protocol    = "TCP"
  target_type = "instance"
  vpc_id      = data.aws_vpc.default.id

  health_check {
    protocol = "TCP"
    port     = "80"
  }
}

resource "aws_lb_target_group_attachment" "hors_production_80" {
  count            = 1
  target_group_arn = aws_lb_target_group.hors_production_80.arn
  target_id        = aws_instance.hors_production[count.index].id
  port             = 80
}

resource "aws_lb_listener" "hors_production_80" {
  load_balancer_arn = aws_lb.hors_production.arn
  port              = 80
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.hors_production_80.arn
  }
}

resource "aws_lb_target_group" "hors_production_443" {
  name        = "mon-app-hors-production-443"
  port        = 443
  protocol    = "TCP"
  target_type = "instance"
  vpc_id      = data.aws_vpc.default.id

  health_check {
    protocol = "TCP"
    port     = "80"
  }
}

resource "aws_lb_target_group_attachment" "hors_production_443" {
  count            = 1
  target_group_arn = aws_lb_target_group.hors_production_443.arn
  target_id        = aws_instance.hors_production[count.index].id
  port             = 443
}

resource "aws_lb_listener" "hors_production_443" {
  load_balancer_arn = aws_lb.hors_production.arn
  port              = 443
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.hors_production_443.arn
  }
}

# --- production : répartiteur
resource "aws_lb" "production" {
  name               = "mon-app-production"
  load_balancer_type = "network"
  internal           = false
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "production_80" {
  name        = "mon-app-production-80"
  port        = 80
  protocol    = "TCP"
  target_type = "instance"
  vpc_id      = data.aws_vpc.default.id

  health_check {
    protocol = "TCP"
    port     = "80"
  }
}

resource "aws_lb_target_group_attachment" "production_80" {
  count            = 1
  target_group_arn = aws_lb_target_group.production_80.arn
  target_id        = aws_instance.production[count.index].id
  port             = 80
}

resource "aws_lb_listener" "production_80" {
  load_balancer_arn = aws_lb.production.arn
  port              = 80
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.production_80.arn
  }
}

resource "aws_lb_target_group" "production_443" {
  name        = "mon-app-production-443"
  port        = 443
  protocol    = "TCP"
  target_type = "instance"
  vpc_id      = data.aws_vpc.default.id

  health_check {
    protocol = "TCP"
    port     = "80"
  }
}

resource "aws_lb_target_group_attachment" "production_443" {
  count            = 1
  target_group_arn = aws_lb_target_group.production_443.arn
  target_id        = aws_instance.production[count.index].id
  port             = 443
}

resource "aws_lb_listener" "production_443" {
  load_balancer_arn = aws_lb.production.arn
  port              = 443
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.production_443.arn
  }
}

# --- Amazon Route 53
resource "aws_route53_zone" "main" {
  name = "boutique.fr"
}

resource "aws_route53_record" "hors_production" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "boutique-hors-production.boutique.fr"
  type    = "A"

  alias {
    name                   = aws_lb.hors_production.dns_name
    zone_id                = aws_lb.hors_production.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "production" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "boutique.boutique.fr"
  type    = "A"

  alias {
    name                   = aws_lb.production.dns_name
    zone_id                = aws_lb.production.zone_id
    evaluate_target_health = true
  }
}
