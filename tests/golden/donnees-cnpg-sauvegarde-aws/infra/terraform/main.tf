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

# --- EKS Pod Identity (identités de charge de travail)
resource "aws_eks_addon" "pod_identity" {
  cluster_name = module.eks.cluster_name
  addon_name   = "eks-pod-identity-agent"
}

# --- Sauvegardes CloudNativePG (plugin Barman Cloud)
resource "aws_s3_bucket" "db_backups" {
  bucket = "mon-app-db-backups"
}

resource "aws_s3_bucket_versioning" "db_backups" {
  bucket = aws_s3_bucket.db_backups.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "db_backups" {
  bucket                  = aws_s3_bucket.db_backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_iam_role" "db_backups" {
  name = "mon-app-db-backups"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "pods.eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
}

resource "aws_iam_role_policy" "db_backups" {
  name = "sauvegardes"
  role = aws_iam_role.db_backups.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketLocation"]
      Resource = [aws_s3_bucket.db_backups.arn, "${aws_s3_bucket.db_backups.arn}/*"]
    }]
  })
}

resource "aws_eks_pod_identity_association" "db_backups_mon_app" {
  cluster_name    = module.eks.cluster_name
  namespace       = "mon-app"
  service_account = "mon-app-pg"
  role_arn        = aws_iam_role.db_backups.arn
}

resource "aws_eks_pod_identity_association" "db_backups_mon_app_staging" {
  cluster_name    = module.eks.cluster_name
  namespace       = "mon-app-staging"
  service_account = "mon-app-pg"
  role_arn        = aws_iam_role.db_backups.arn
}
