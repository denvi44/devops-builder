"""Script de déclaration des variables CI : chaque variable « à déclarer » de PIPELINE.md.

Le script ne contient aucune valeur : il les lit dans l'environnement, dans un fichier
(NOM_FILE) ou au clavier, puis les déclare avec l'outil officiel de la forge.
"""

from __future__ import annotations

import shlex

from ..ir import IR, Variable
from .common import HEADER

CI_VARIABLES = "scripts/ci-variables.sh"
SUPPORTED = {"gitlab-ci": "GitLab (glab)", "github-actions": "GitHub (gh)", "gitea-actions": "Gitea (API)",
             "azure-pipelines": "Azure Pipelines (az)"}

_COMMON = r"""#!/usr/bin/env bash
# @HEADER@
# Déclare dans @TARGET@ les variables CI listées dans PIPELINE.md.
# Aucune valeur n'est écrite dans le dépôt. Pour chaque variable, la valeur vient, dans l'ordre :
#   1. de la variable d'environnement du même nom   REGISTRY_PASSWORD=… scripts/ci-variables.sh
#   2. du fichier désigné par NOM_FILE              SSH_PRIVATE_KEY_FILE=~/.ssh/deploy scripts/ci-variables.sh
#   3. d'une saisie au clavier (masquée pour les secrets) ; une saisie vide saute la variable.
#
#   scripts/ci-variables.sh            déclare les variables
#   scripts/ci-variables.sh --dry-run  affiche ce qui serait déclaré, sans rien envoyer
@EXTRA_HELP@set -euo pipefail

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
"""

_GITLAB = r"""need glab "https://gitlab.com/gitlab-org/cli (puis glab auth login)"

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
"""

_GITHUB = r"""need gh "https://cli.github.com (puis gh auth login)"

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
"""

_GITEA = r"""need curl "https://curl.se"
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
"""

_AZURE = r"""need az "https://learn.microsoft.com/cli/azure/install-azure-cli (puis az extension add --name azure-devops)"

# Variables du pipeline AZ_PIPELINE (son nom dans Azure DevOps). Organisation et projet :
# az devops configure --defaults organization=https://dev.azure.com/ORG project=PROJET
# Les secrets passent par une variable d'environnement, jamais par la ligne de commande.
if [ -z "${AZ_PIPELINE:-}" ]; then
  read -rp "Nom du pipeline dans Azure DevOps : " AZ_PIPELINE
fi

send() {
  local name="$1" secret="$2" v="$4"
  if [ "$secret" = 1 ]; then
    env "AZURE_DEVOPS_EXT_PIPELINE_VAR_$name=$v" az pipelines variable create --name "$name" --secret true \
        --pipeline-name "$AZ_PIPELINE" --output none </dev/null 2>/dev/null \
      || env "AZURE_DEVOPS_EXT_PIPELINE_VAR_$name=$v" az pipelines variable update --name "$name" --secret true \
        --prompt-value true --pipeline-name "$AZ_PIPELINE" --output none </dev/null
  else
    az pipelines variable create --name "$name" --value "$v" --pipeline-name "$AZ_PIPELINE" --output none 2>/dev/null \
      || az pipelines variable update --name "$name" --value "$v" --pipeline-name "$AZ_PIPELINE" --output none
  fi
}
"""

_BACKENDS = {"gitlab-ci": _GITLAB, "github-actions": _GITHUB, "gitea-actions": _GITEA, "azure-pipelines": _AZURE}

_FOOTER = r"""
echo
if [ "$DRY_RUN" = 1 ]; then
  echo "$done_count à déclarer, $skipped sans valeur (aperçu : rien n'a été envoyé)."
  exit 0
fi
echo "$done_count déclarée(s), $skipped ignorée(s), $failed en échec."
if [ "$failed" -gt 0 ]; then exit 1; fi
"""


def pending(ir: IR) -> list[Variable]:
    """Variables à déclarer : celles dont la valeur n'est pas déjà écrite dans les fichiers."""
    return [v for v in ir.variables if not v.value]


def ci_variables(ir: IR) -> dict[str, str]:
    if ir.ci is None or ir.ci.id not in _BACKENDS:
        return {}
    todo = pending(ir)
    if not todo:
        return {}
    lines = [f"declare_var {v.name} {1 if v.secret else 0} {shlex.quote(v.description)}" for v in todo]
    extra = ""
    if ir.ci.id == "github-actions":
        extra = "#\n# GitHub : les secrets sont déclarés au niveau du dépôt, accessibles à tous ses workflows.\n"
    text = (_COMMON.replace("@HEADER@", HEADER).replace("@TARGET@", SUPPORTED[ir.ci.id])
            .replace("@EXTRA_HELP@", extra)
            + _BACKENDS[ir.ci.id] + "\n" + "\n".join(lines) + "\n" + _FOOTER)
    ir.notes.append(f"`{CI_VARIABLES}` déclare les {len(todo)} variable(s) à renseigner avec "
                    f"{SUPPORTED[ir.ci.id]}, sans écrire leurs valeurs dans le dépôt.")
    return {CI_VARIABLES: text}
