# Généré par DevOps Builder — à relire avant usage.

provider "aws" {
  region = "eu-west-3"
}

# --- Amazon ECR
resource "aws_ecr_repository" "app" {
  name                 = "commandes"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- Amazon EKS (staging)
module "eks_staging" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = "plateforme-preprod"
  kubernetes_version = "1.33"
  vpc_id             = var.vpc_id
  subnet_ids         = var.subnet_ids

  eks_managed_node_groups = {
    default = {
      instance_types = ["t3.large"]
      min_size       = 2
      max_size       = 4
      desired_size   = 2

      iam_role_additional_policies = {
        CloudWatchAgentServerPolicy = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
      }
    }
  }
}

# --- Amazon CloudWatch (Container Insights)
resource "aws_eks_addon" "cloudwatch_staging" {
  cluster_name = module.eks_staging.cluster_name
  addon_name   = "amazon-cloudwatch-observability"
}

# --- Amazon EKS (production)
module "eks_production" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = "plateforme-prod"
  kubernetes_version = "1.33"
  vpc_id             = var.vpc_id
  subnet_ids         = var.subnet_ids

  eks_managed_node_groups = {
    default = {
      instance_types = ["t3.large"]
      min_size       = 2
      max_size       = 4
      desired_size   = 2

      iam_role_additional_policies = {
        CloudWatchAgentServerPolicy = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
      }
    }
  }
}

# --- Amazon CloudWatch (Container Insights)
resource "aws_eks_addon" "cloudwatch_production" {
  cluster_name = module.eks_production.cluster_name
  addon_name   = "amazon-cloudwatch-observability"
}

# --- Amazon S3
# Le bucket plateforme-prod-tfstate porte l'état de cette pile : il est créé à part (amorçage),
# pas par la pile qui l'utilise.

# --- AWS Secrets Manager
resource "aws_secretsmanager_secret" "app" {
  name = "commandes"
}

# --- External Secrets : lecture du coffre par le contrôleur (EKS Pod Identity)
resource "aws_iam_role" "external_secrets" {
  name = "commandes-external-secrets"
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
      Resource = ["arn:aws:secretsmanager:*:*:secret:commandes/*", "arn:aws:secretsmanager:*:*:secret:commandes-staging/*"]
    }]
  })
}

resource "aws_eks_addon" "pod_identity_staging" {
  cluster_name = module.eks_staging.cluster_name
  addon_name   = "eks-pod-identity-agent"
}

resource "aws_eks_pod_identity_association" "external_secrets_staging" {
  cluster_name    = module.eks_staging.cluster_name
  namespace       = "external-secrets"
  service_account = "external-secrets"
  role_arn        = aws_iam_role.external_secrets.arn
}

resource "aws_eks_addon" "pod_identity_production" {
  cluster_name = module.eks_production.cluster_name
  addon_name   = "eks-pod-identity-agent"
}

resource "aws_eks_pod_identity_association" "external_secrets_production" {
  cluster_name    = module.eks_production.cluster_name
  namespace       = "external-secrets"
  service_account = "external-secrets"
  role_arn        = aws_iam_role.external_secrets.arn
}
