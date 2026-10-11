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
