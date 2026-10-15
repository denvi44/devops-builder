#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Déclare dans GitLab (glab) les variables CI listées dans PIPELINE.md.
# Aucune valeur n'est écrite dans le dépôt. Pour chaque variable, la valeur vient, dans l'ordre :
#   1. de la variable d'environnement du même nom   REGISTRY_PASSWORD=… scripts/ci-variables.sh
#   2. du fichier désigné par NOM_FILE              SSH_PRIVATE_KEY_FILE=~/.ssh/deploy scripts/ci-variables.sh
#   3. d'une saisie au clavier (masquée pour les secrets) ; une saisie vide saute la variable.
#
#   scripts/ci-variables.sh            déclare les variables
#   scripts/ci-variables.sh --dry-run  affiche ce qui serait déclaré, sans rien envoyer
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
need glab "https://gitlab.com/gitlab-org/cli (puis glab auth login)"

# Les secrets compatibles avec le masquage de GitLab (une ligne, 8 caractères ou plus,
# alphabet base64 et @ : . ~) sont masqués dans les journaux ; les autres sont déclarés
# sans masquage, avec un avertissement. Le dépôt visé est celui du dossier courant (ou GITLAB_REPO).
send() {
  local name="$1" secret="$2" desc="$3" v="$4" flags=()
  if [ -n "${GITLAB_REPO:-}" ]; then flags+=(--repo "$GITLAB_REPO"); fi
  if [ "$secret" = 1 ]; then
    if [[ "$v" =~ ^[A-Za-z0-9+/=@:.~]{8,}$ ]]; then
      flags+=(--masked)
    else
      echo "  ! $name ne peut pas être masquée par GitLab (format) : protéger la variable dans Settings › CI/CD." >&2
    fi
  fi
  printf '%s' "$v" | glab variable set "$name" --description "$desc" ${flags[@]+"${flags[@]}"} >/dev/null 2>&1 \
    || printf '%s' "$v" | glab variable update "$name" --description "$desc" ${flags[@]+"${flags[@]}"} >/dev/null
}

declare_var REGISTRY_USER 1 'Compte de publication sur europe-west9-docker.pkg.dev'
declare_var REGISTRY_PASSWORD 1 'Mot de passe ou jeton de publication sur europe-west9-docker.pkg.dev'
declare_var GCP_WORKLOAD_IDENTITY_PROVIDER 0 'Fournisseur Workload Identity Federation'
declare_var GCP_SERVICE_ACCOUNT 0 'Compte de service impersonné par la CI'
declare_var GCP_INFRA_SERVICE_ACCOUNT 0 'Compte de service des jobs d'"'"'infrastructure (plan, apply)'
declare_var RENOVATE_TOKEN 1 'Jeton de la forge autorisé à ouvrir des merge requests (Renovate)'

echo
if [ "$DRY_RUN" = 1 ]; then
  echo "$done_count à déclarer, $skipped sans valeur (aperçu : rien n'a été envoyé)."
  exit 0
fi
echo "$done_count déclarée(s), $skipped ignorée(s), $failed en échec."
if [ "$failed" -gt 0 ]; then exit 1; fi
