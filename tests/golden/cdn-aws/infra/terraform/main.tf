# Généré par DevOps Builder — à relire avant usage.

provider "aws" {
  region = "eu-west-3"
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

# --- Amazon S3
# Le bucket mon-projet-tfstate porte l'état de cette pile : il est créé à part (amorçage),
# pas par la pile qui l'utilise.

# --- Réseau par défaut du compte AWS (aucune brique Amazon VPC)
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
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

# --- Amazon EC2 : hors-production (Préproduction)
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

# --- Amazon CloudFront et AWS WAF
# Un pare-feu CloudFront se crée obligatoirement en us-east-1.
resource "aws_wafv2_web_acl" "cdn" {
  provider = aws.us_east_1
  name     = "mon-app-cdn"
  scope    = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "regles-communes"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "mon-app-regles-communes"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "limite-par-adresse"
    priority = 2

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 10000
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "mon-app-limite-par-adresse"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "mon-app-cdn"
    sampled_requests_enabled   = true
  }
}

resource "aws_cloudfront_distribution" "main" {
  enabled         = true
  comment         = "mon-app"
  is_ipv6_enabled = true
  price_class     = "PriceClass_100"
  web_acl_id      = aws_wafv2_web_acl.cdn.arn

  origin {
    domain_name = aws_lb.production.dns_name
    origin_id   = "app"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id         = "app"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
