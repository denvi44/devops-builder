# Généré par DevOps Builder — à relire avant usage.

provider "aws" {
  region = "eu-west-3"
}

# --- Amazon ECR
resource "aws_ecr_repository" "app" {
  name                 = "boutique"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- Amazon EKS
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = "boutique"
  kubernetes_version = "1.36"
  vpc_id             = var.vpc_id
  subnet_ids         = var.subnet_ids

  eks_managed_node_groups = {
    default = {
      instance_types = ["t3.large"]
      min_size       = 2
      max_size       = 4
      desired_size   = 2
    }
  }
}

# --- Amazon S3
# Le bucket boutique-tfstate porte l'état de cette pile : il est créé à part (amorçage),
# pas par la pile qui l'utilise.

# --- Amazon RDS (Préproduction)
resource "aws_db_instance" "db_staging" {
  identifier                  = "boutique-staging"
  engine                      = "postgres"
  engine_version              = "17"
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  max_allocated_storage       = 100
  storage_encrypted           = true
  db_name                     = "app"
  username                    = "app"
  manage_master_user_password = true
  db_subnet_group_name        = var.db_subnet_group
  vpc_security_group_ids      = var.db_security_group_ids
  multi_az                    = false
  backup_retention_period     = 1
  deletion_protection         = false
  skip_final_snapshot         = true
}

# --- Amazon RDS (Production)
resource "aws_db_instance" "db_production" {
  identifier                  = "boutique"
  engine                      = "postgres"
  engine_version              = "17"
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  max_allocated_storage       = 100
  storage_encrypted           = true
  db_name                     = "app"
  username                    = "app"
  manage_master_user_password = true
  db_subnet_group_name        = var.db_subnet_group
  vpc_security_group_ids      = var.db_security_group_ids
  multi_az                    = true
  backup_retention_period     = 7
  deletion_protection         = true
  skip_final_snapshot         = false
  final_snapshot_identifier   = "boutique-final"
}
