"""Floci, émulateur AWS local : environnement de développement, tests de l'application, plan de l'IaC.

Floci écoute sur le port 4566 et accepte n'importe quels identifiants (test/test). Les services qui
lancent de vrais conteneurs (Lambda, RDS, EKS, ECS…) ont besoin du socket Docker : en local le
fichier Compose le monte ; dans la CI, Floci tourne en conteneur annexe sans socket, ce qui suffit
pour un plan et pour les services émulés en mémoire (S3, SQS, DynamoDB, IAM, Secrets Manager…).
"""

from __future__ import annotations

from ..ir import FLOCI_IMAGE, IR, SERVICE_CI, floci_in_ci, floci_region
from .common import HEADER, dump_yaml

COMPOSE = "dev/floci/compose.yaml"
ENV_FILE = "dev/floci/aws.env"
TF_SCRIPT = "scripts/tf-floci.sh"
# Points d'accès redirigés vers Floci pour le plan de la pile (clés du bloc endpoints du provider aws)
ENDPOINTS = ["acm", "autoscaling", "cloudwatch", "dynamodb", "ec2", "ecr", "eks", "elasticache", "elb", "elbv2",
             "iam", "kms", "lambda", "logs", "rds", "route53", "s3", "secretsmanager", "sns", "sqs", "ssm", "sts"]

_TF = r"""#!/usr/bin/env bash
# @HEADER@
# Joue la pile Terraform / OpenTofu de infra/terraform sur Floci, l'émulateur AWS local :
# ni compte AWS, ni identifiants, ni état distant (un backend local temporaire le remplace).
#
#   scripts/tf-floci.sh plan     init et plan (ce que fait la CI)
#   scripts/tf-floci.sh apply    plan, apply puis destroy ; KEEP=1 garde les ressources
#
# FLOCI_ENDPOINT=http://hote:4566  Floci déjà lancé ; sinon le script le démarre avec Docker
# TF=tofu|terraform                outil à utiliser (défaut : @TF@)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-plan}"
TF_BIN="${TF:-@TF@}"
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
    -e FLOCI_DEFAULT_REGION=@REGION@ @IMAGE@ >/dev/null
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
  region                      = "@REGION@"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
@ENDPOINTS@
  }
}
EOF
@TFVARS@
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
"""


def floci_files(ir: IR) -> dict[str, str]:
    if not ir.has("floci"):
        return {}
    region = floci_region(ir)
    service = {
        "image": FLOCI_IMAGE,
        "ports": ["4566:4566"],
        "user": "root",  # accès au socket Docker (Lambda, RDS, EKS… lancent de vrais conteneurs)
        "environment": {"FLOCI_DEFAULT_REGION": region, "FLOCI_STORAGE_MODE": "hybrid"},
        "volumes": ["floci-data:/app/data", "/var/run/docker.sock:/var/run/docker.sock"],
    }
    files = {
        COMPOSE: dump_yaml({"name": f"{ir.app}-floci", "services": {"floci": service}, "volumes": {"floci-data": {}}},
                           f"{HEADER} Émulateur AWS local : docker compose -f {COMPOSE} up -d"),
        ENV_FILE: (f"# {HEADER}\n# Pointe les SDK et la CLI AWS vers Floci : set -a; . {ENV_FILE}; set +a\n"
                   f"AWS_ENDPOINT_URL=http://localhost:4566\nAWS_ACCESS_KEY_ID=test\nAWS_SECRET_ACCESS_KEY=test\n"
                   f"AWS_DEFAULT_REGION={region}\nAWS_REGION={region}\n"),
    }
    tf = bool(ir.iac and ir.iac.id in ("terraform", "opentofu")) and {p.id for p in ir.providers} == {"aws"}
    if tf:
        from .iac import required_vars
        tvs = required_vars(ir)
        tfvars = ""
        if tvs:
            tfvars = ("cat > \"$WORK/floci.auto.tfvars\" <<'EOF'\n"
                      + "".join(f"{tv.name} = {tv.dummy}\n" for tv in tvs) + "EOF")
        width = max(len(e) for e in ENDPOINTS)
        endpoints = "\n".join(f"    {e.ljust(width)} = \"$FLOCI_ENDPOINT\"" for e in ENDPOINTS)
        files[TF_SCRIPT] = (_TF.replace("@HEADER@", HEADER).replace("@TF@", ir.iac_cmd)
                            .replace("@REGION@", region).replace("@IMAGE@", FLOCI_IMAGE)
                            .replace("@ENDPOINTS@", endpoints).replace("@TFVARS@", tfvars))
    notes = [f"Floci : `docker compose -f {COMPOSE} up -d` lance l'émulateur AWS sur le port 4566 ; "
             f"`{ENV_FILE}` y pointe les SDK et la CLI (identifiants factices test/test)."]
    if floci_in_ci(ir):
        if ir.has("unit-tests"):
            notes.append("Floci tourne à côté des tests unitaires dans la CI : AWS_ENDPOINT_URL désigne l'émulateur.")
        if tf:
            notes.append(f"`{TF_SCRIPT} plan` joue la pile sur Floci, sans compte AWS (job CI non bloquant) ; "
                         "`apply` crée puis détruit les ressources en local. Les services à conteneurs (EKS, RDS, "
                         "Lambda) demandent le socket Docker, monté seulement par le script lancé en local.")
    elif ir.ci is not None:
        notes.append(f"Floci n'est pas démarré par {ir.ci.name} (conteneurs annexes par job : "
                     f"{', '.join(ir.catalog[c].name for c in SERVICE_CI if c in ir.catalog)}) : "
                     "le lancer sur l'agent pour les tests qui appellent AWS.")
    elif tf:
        notes.append(f"`{TF_SCRIPT} plan` joue la pile sur Floci, sans compte AWS.")
    ir.notes += notes
    ir.cover("floci")
    return files
