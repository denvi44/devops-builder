#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Joue la pile Terraform / OpenTofu de infra/terraform sur Floci, l'émulateur AWS local :
# ni compte AWS, ni identifiants, ni état distant (un backend local temporaire le remplace).
#
#   scripts/tf-floci.sh plan     init et plan (ce que fait la CI)
#   scripts/tf-floci.sh apply    plan, apply puis destroy ; KEEP=1 garde les ressources
#
# FLOCI_ENDPOINT=http://hote:4566  Floci déjà lancé ; sinon le script le démarre avec Docker
# TF=tofu|terraform                outil à utiliser (défaut : tofu)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-plan}"
TF_BIN="${TF:-tofu}"
case "$ACTION" in plan|apply) ;; *) echo "Action inconnue : $ACTION (plan ou apply)" >&2; exit 2 ;; esac
command -v "$TF_BIN" >/dev/null 2>&1 || { echo "Outil manquant : $TF_BIN" >&2; exit 3; }

STARTED=""
WORK="$(mktemp -d)"
cleanup() {
  rm -rf "$WORK"
  if [ -n "$STARTED" ]; then docker rm -f devops-builder-floci >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

if [ -z "${FLOCI_ENDPOINT:-}" ]; then
  command -v docker >/dev/null 2>&1 || { echo "Docker est requis pour démarrer Floci (ou FLOCI_ENDPOINT)." >&2; exit 3; }
  echo "==> Démarrage de Floci"
  docker run -d --name devops-builder-floci -p 4566:4566 -u root \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -e FLOCI_DEFAULT_REGION=eu-west-3 floci/floci:2.2.0 >/dev/null
  STARTED=1
  FLOCI_ENDPOINT="http://localhost:4566"
fi
for _ in $(seq 1 60); do
  if curl -fsS "$FLOCI_ENDPOINT/_localstack/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "$FLOCI_ENDPOINT/_localstack/health" >/dev/null || { echo "Floci ne répond pas sur $FLOCI_ENDPOINT" >&2; exit 1; }

cp -R "$ROOT/infra/terraform/." "$WORK/"
rm -rf "$WORK/.terraform" "$WORK"/*.tfstate* "$WORK"/*.tfplan
cat > "$WORK/floci_override.tf" <<EOF
terraform {
  backend "local" {}
}

provider "aws" {
  region                      = "eu-west-3"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    acm            = "$FLOCI_ENDPOINT"
    autoscaling    = "$FLOCI_ENDPOINT"
    cloudwatch     = "$FLOCI_ENDPOINT"
    dynamodb       = "$FLOCI_ENDPOINT"
    ec2            = "$FLOCI_ENDPOINT"
    ecr            = "$FLOCI_ENDPOINT"
    eks            = "$FLOCI_ENDPOINT"
    elasticache    = "$FLOCI_ENDPOINT"
    elb            = "$FLOCI_ENDPOINT"
    elbv2          = "$FLOCI_ENDPOINT"
    iam            = "$FLOCI_ENDPOINT"
    kms            = "$FLOCI_ENDPOINT"
    lambda         = "$FLOCI_ENDPOINT"
    logs           = "$FLOCI_ENDPOINT"
    rds            = "$FLOCI_ENDPOINT"
    route53        = "$FLOCI_ENDPOINT"
    s3             = "$FLOCI_ENDPOINT"
    secretsmanager = "$FLOCI_ENDPOINT"
    sns            = "$FLOCI_ENDPOINT"
    sqs            = "$FLOCI_ENDPOINT"
    ssm            = "$FLOCI_ENDPOINT"
    sts            = "$FLOCI_ENDPOINT"
  }
}
EOF
cat > "$WORK/floci.auto.tfvars" <<'EOF'
vpc_id = "vpc-0f10c1"
subnet_ids = ["subnet-0f10c1a", "subnet-0f10c1b"]
db_subnet_group = "floci"
db_security_group_ids = ["sg-0f10c1"]
EOF
cd "$WORK"
echo "==> $TF_BIN init"
"$TF_BIN" init -input=false -no-color >/dev/null
echo "==> $TF_BIN plan"
"$TF_BIN" plan -input=false -no-color -out=floci.tfplan
if [ "$ACTION" = apply ]; then
  echo "==> $TF_BIN apply"
  "$TF_BIN" apply -input=false -no-color floci.tfplan
  if [ "${KEEP:-0}" != 1 ]; then
    echo "==> $TF_BIN destroy"
    "$TF_BIN" destroy -input=false -no-color -auto-approve
  fi
fi
echo "==> Pile jouée sur Floci ($ACTION)."
