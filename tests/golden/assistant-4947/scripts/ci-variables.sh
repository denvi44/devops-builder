#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Déclare dans Gitea (API) les variables CI listées dans PIPELINE.md.
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
need curl "https://curl.se"
need jq "https://jqlang.org"

# Instance et dépôt : GITEA_URL (https://gitea.exemple.fr) et GITEA_REPO (propriétaire/depot),
# déduits du dépôt distant « origin » s'ils ne sont pas fournis. GITEA_TOKEN : jeton d'accès
# avec la portée « write:repository ».
if [ -z "${GITEA_URL:-}" ] || [ -z "${GITEA_REPO:-}" ]; then
  remote="$(git remote get-url origin 2>/dev/null || true)"
  remote="${remote%.git}"
  case "$remote" in
    http*://*) host_path="${remote#*://}"; host_path="${host_path#*@}" ;;
    ssh://*) host_path="${remote#ssh://}"; host_path="${host_path#*@}"; host_path="${host_path%%:*}/${host_path#*/}" ;;
    *@*:*) host_path="${remote#*@}"; host_path="${host_path/://}" ;;
    *) host_path="" ;;
  esac
  GITEA_URL="${GITEA_URL:-https://${host_path%%/*}}"
  GITEA_REPO="${GITEA_REPO:-${host_path#*/}}"
fi
if [ -z "${GITEA_TOKEN:-}" ] && [ "$DRY_RUN" = 0 ]; then
  read -rsp "Jeton d'accès Gitea (write:repository) : " GITEA_TOKEN
  echo >&2
fi
echo "Dépôt : $GITEA_URL/$GITEA_REPO"

api() {  # api MÉTHODE CHEMIN < corps JSON ; affiche le code HTTP
  curl -sS -o /dev/null -w '%{http_code}' -X "$1" \
    -H "Authorization: token $GITEA_TOKEN" -H "Content-Type: application/json" \
    --data-binary @- "$GITEA_URL/api/v1/repos/$GITEA_REPO/actions/$2"
}

send() {
  local name="$1" secret="$2" desc="$3" v="$4" code
  if [ "$secret" = 1 ]; then
    code="$(jq -n --arg v "$v" --arg d "$desc" '{data: $v, description: $d}' | api PUT "secrets/$name")"
  else
    code="$(jq -n --arg v "$v" --arg d "$desc" '{value: $v, description: $d}' | api POST "variables/$name")"
    if [ "$code" = 409 ]; then
      code="$(jq -n --arg v "$v" --arg d "$desc" '{value: $v, description: $d}' | api PUT "variables/$name")"
    fi
  fi
  case "$code" in 200|201|204) return 0 ;; *) echo "  HTTP $code" >&2; return 1 ;; esac
}

declare_var SONAR_HOST_URL 0 'URL du serveur SonarQube'
declare_var SONAR_TOKEN 1 'Jeton d'"'"'analyse SonarQube'
declare_var REGISTRY_USER 1 'Compte de publication sur registry.example.com'
declare_var REGISTRY_PASSWORD 1 'Mot de passe ou jeton de publication sur registry.example.com'
declare_var OVH_APPLICATION_KEY 1 'Clé d'"'"'application OVHcloud'
declare_var OVH_APPLICATION_SECRET 1 'Secret d'"'"'application OVHcloud'
declare_var OVH_CONSUMER_KEY 1 'Clé consommateur OVHcloud'
declare_var GITOPS_TOKEN 1 'Jeton autorisé à pousser sur le dépôt GitOps'
declare_var GITOPS_REPO 0 'Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git)'
declare_var RENOVATE_TOKEN 1 'Jeton de la forge autorisé à ouvrir des merge requests (Renovate)'

echo
if [ "$DRY_RUN" = 1 ]; then
  echo "$done_count à déclarer, $skipped sans valeur (aperçu : rien n'a été envoyé)."
  exit 0
fi
echo "$done_count déclarée(s), $skipped ignorée(s), $failed en échec."
if [ "$failed" -gt 0 ]; then exit 1; fi
