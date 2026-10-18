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
  secret_string = "postgresql://app:${urlencode(jsondecode(data.aws_secretsmanager_secret_version.db_staging_master.secret_string)["password"])}@${aws_db_instance.db_staging.address}:5432/app"
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
  secret_string = "postgresql://app:${urlencode(jsondecode(data.aws_secretsmanager_secret_version.db_production_master.secret_string)["password"])}@${aws_db_instance.db_production.address}:5432/app"
}
