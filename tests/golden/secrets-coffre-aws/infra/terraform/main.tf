# Généré par DevOps Builder — à relire avant usage.

provider "aws" {
  region = "eu-west-3"
}

# --- Amazon ECR
resource "aws_ecr_repository" "app" {
  name                 = "mon-app"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- Amazon EKS
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = "mon-cluster"
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
# Le bucket mon-projet-tfstate porte l'état de cette pile : il est créé à part (amorçage),
# pas par la pile qui l'utilise.

# --- Amazon RDS (Préproduction)
resource "aws_db_instance" "db_staging" {
  identifier                  = "mon-app-staging"
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
  identifier                  = "mon-app"
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
  final_snapshot_identifier   = "mon-app-final"
}

# --- Secret mon-app-staging/aws-rds (Amazon RDS)
data "aws_secretsmanager_secret_version" "db_staging_master" {
  secret_id = aws_db_instance.db_staging.master_user_secret[0].secret_arn
}

resource "aws_secretsmanager_secret" "secret_aws_rds_staging" {
  name                    = "mon-app-staging/aws-rds"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "secret_aws_rds_staging" {
  secret_id     = aws_secretsmanager_secret.secret_aws_rds_staging.id
  secret_string = jsonencode({ url = "postgresql://app:${urlencode(jsondecode(data.aws_secretsmanager_secret_version.db_staging_master.secret_string)["password"])}@${aws_db_instance.db_staging.address}:5432/app" })
}

# --- Secret mon-app/aws-rds (Amazon RDS)
data "aws_secretsmanager_secret_version" "db_production_master" {
  secret_id = aws_db_instance.db_production.master_user_secret[0].secret_arn
}

resource "aws_secretsmanager_secret" "secret_aws_rds_production" {
  name = "mon-app/aws-rds"
}

resource "aws_secretsmanager_secret_version" "secret_aws_rds_production" {
  secret_id     = aws_secretsmanager_secret.secret_aws_rds_production.id
  secret_string = jsonencode({ url = "postgresql://app:${urlencode(jsondecode(data.aws_secretsmanager_secret_version.db_production_master.secret_string)["password"])}@${aws_db_instance.db_production.address}:5432/app" })
}

# --- Secret mon-app-staging/valkey (Valkey)
resource "random_password" "secret_valkey_staging" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "aws_secretsmanager_secret" "secret_valkey_staging" {
  name                    = "mon-app-staging/valkey"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "secret_valkey_staging" {
  secret_id     = aws_secretsmanager_secret.secret_valkey_staging.id
  secret_string = jsonencode({ password = random_password.secret_valkey_staging.result })
}

# --- Secret mon-app/valkey (Valkey)
resource "random_password" "secret_valkey_production" {
  length           = 32
  special          = true
  override_special = "-_.~"
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
}

resource "aws_secretsmanager_secret" "secret_valkey_production" {
  name = "mon-app/valkey"
}

resource "aws_secretsmanager_secret_version" "secret_valkey_production" {
  secret_id     = aws_secretsmanager_secret.secret_valkey_production.id
  secret_string = jsonencode({ password = random_password.secret_valkey_production.result })
}

# --- EKS Pod Identity (identités de charge de travail)
resource "aws_eks_addon" "pod_identity" {
  cluster_name = module.eks.cluster_name
  addon_name   = "eks-pod-identity-agent"
}

# --- External Secrets : lecture du coffre par le contrôleur (EKS Pod Identity)
resource "aws_iam_role" "external_secrets" {
  name = "mon-app-external-secrets"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "pods.eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
}

resource "aws_iam_role_policy" "external_secrets" {
  name = "lecture-secrets"
  role = aws_iam_role.external_secrets.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = ["arn:aws:secretsmanager:*:*:secret:mon-app/*", "arn:aws:secretsmanager:*:*:secret:mon-app-staging/*"]
    }]
  })
}

resource "aws_eks_pod_identity_association" "external_secrets" {
  cluster_name    = module.eks.cluster_name
  namespace       = "external-secrets"
  service_account = "external-secrets"
  role_arn        = aws_iam_role.external_secrets.arn
}
