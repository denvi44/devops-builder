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

  # accès Kubernetes : l'identité qui applique la pile, le rôle de déploiement de la CI et les personnes
  # déclarées dans cluster_admin_arns (l'identité qui applique change après le premier apply depuis le poste)
  enable_cluster_creator_admin_permissions = true
  access_entries = {
    for name, arn in merge({ ci = var.ci_deploy_role_arn }, { for i, a in var.cluster_admin_arns : "admin-${i}" => a }) :
    name => {
      principal_arn = arn
      policy_associations = {
        admin = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    } if arn != ""
  }

  eks_managed_node_groups = {
    default = {
      instance_types = ["t3.large"]
      min_size       = 2
      max_size       = 4
      desired_size   = 2
    }
  }
}
