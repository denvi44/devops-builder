#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Déclare dans GitHub (gh) les variables CI listées dans PIPELINE.md.
# Aucune valeur n'est écrite dans le dépôt. Pour chaque variable, la valeur vient, dans l'ordre :
#   1. de la variable d'environnement du même nom   REGISTRY_PASSWORD=… scripts/ci-variables.sh
#   2. du fichier désigné par NOM_FILE              SSH_PRIVATE_KEY_FILE=~/.ssh/deploy scripts/ci-variables.sh
#   3. d'une saisie au clavier (masquée pour les secrets) ; une saisie vide saute la variable.
#
#   scripts/ci-variables.sh            déclare les variables
#   scripts/ci-variables.sh --dry-run  affiche ce qui serait déclaré, sans rien envoyer
#
# GitHub : les secrets sont déclarés au niveau du dépôt, accessibles à tous ses workflows.
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=1; fi
done_count=0
skipped=0
failed=0

need() {
  if command -v "$1" >/dev/null 2>&1; then return 0; fi
  echo "Outil manquant : $1 — $2" >&2
  if [ "$DRY_RUN" = 0 ]; then exit 3; fi
}

# value_of NOM SECRET : affiche la valeur trouvée (vide si aucune).
value_of() {
  local name="$1" secret="$2" file_var="${1}_FILE" v=""
  if [ -n "${!name:-}" ]; then
    v="${!name}"
  elif [ -n "${!file_var:-}" ]; then
    v="$(cat "${!file_var}"; printf x)"   # garde le saut de ligne final (clés SSH)
    v="${v%x}"
  elif [ -t 0 ]; then
    if [ "$secret" = 1 ]; then
      read -rsp "  $name (masqué ; vide pour passer) : " v
      echo >&2
    else
      read -rp "  $name (vide pour passer) : " v
    fi
  fi
  printf '%s' "$v"
}

result() {  # result NOM CODE
  if [ "$2" = 0 ]; then
    echo "✓ $1"
    done_count=$((done_count + 1))
  else
    echo "✗ $1" >&2
    failed=$((failed + 1))
  fi
}

declare_var() {  # declare_var NOM SECRET DESCRIPTION
  local name="$1" secret="$2" desc="$3" v
  echo "$name — $desc"
  v="$(value_of "$name" "$secret"; printf x)"
  v="${v%x}"
  if [ -z "$v" ]; then
    echo "· $name : ignorée (aucune valeur)"
    skipped=$((skipped + 1))
    return 0
  fi
  if [ "$DRY_RUN" = 1 ]; then
    echo "· $name : serait déclarée ($([ "$secret" = 1 ] && echo secret || echo variable), ${#v} caractères)"
    done_count=$((done_count + 1))
    return 0
  fi
  set +e
  send "$name" "$secret" "$desc" "$v"
  local code=$?
  set -e
  result "$name" "$code"
}
need gh "https://cli.github.com (puis gh auth login)"

# Secrets : gh secret set ; variables non secrètes : gh variable set (contexte « vars »).
# Le dépôt visé est celui du dossier courant (ou GH_REPO=propriétaire/depot).
send() {
  local name="$1" secret="$2" v="$4"
  if [ "$secret" = 1 ]; then
    printf '%s' "$v" | gh secret set "$name" >/dev/null
  else
    gh variable set "$name" --body "$v" >/dev/null
  fi
}

declare_var AWS_ACCOUNT_ID 0 'Identifiant du compte AWS du registre ECR'
declare_var INFRACOST_API_KEY 1 'Clé d'"'"'API Infracost (gratuite, infracost auth login)'
declare_var TF_VAR_vpc_id 0 'VPC du cluster EKS (variable Terraform vpc_id, ex. "vpc-0123456789abcdef0")'
declare_var TF_VAR_subnet_ids 0 'Sous-réseaux privés du cluster (variable Terraform subnet_ids, ex. ["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"])'
declare_var TF_VAR_db_subnet_group 0 'Groupe de sous-réseaux privés des instances RDS (variable Terraform db_subnet_group, ex. "rds-prive")'
declare_var TF_VAR_db_security_group_ids 0 'Groupes de sécurité autorisant l'"'"'application à joindre la base (variable Terraform db_security_group_ids, ex. ["sg-0123456789abcdef0"])'
declare_var DATABASE_URL_STAGING 1 'URL de connexion à Amazon RDS (Préproduction), lue par l'"'"'application dans DATABASE_URL ; à composer après création de l'"'"'instance (sorties Terraform)'
declare_var DATABASE_URL_PRODUCTION 1 'URL de connexion à Amazon RDS (Production), lue par l'"'"'application dans DATABASE_URL ; à composer après création de l'"'"'instance (sorties Terraform)'
declare_var AWS_ROLE_ARN 0 'Rôle IAM assumé par la CI via OIDC'
declare_var AWS_INFRA_ROLE_ARN 0 'Rôle IAM des jobs d'"'"'infrastructure (plan, apply), assumé via OIDC'

echo
if [ "$DRY_RUN" = 1 ]; then
  echo "$done_count à déclarer, $skipped sans valeur (aperçu : rien n'a été envoyé)."
  exit 0
fi
echo "$done_count déclarée(s), $skipped ignorée(s), $failed en échec."
if [ "$failed" -gt 0 ]; then exit 1; fi
