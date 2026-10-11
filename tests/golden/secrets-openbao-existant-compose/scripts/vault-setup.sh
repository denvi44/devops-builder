#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Configure OpenBao pour mon-app, sans rien supprimer ; relançable sans risque :
#   moteur KV v2 « apps », politique de lecture mon-app-ci-read,
#   connexion JWT de la CI (GitLab, rôle « mon-app-ci »)
#
#   VAULT_ADDR=https://… VAULT_TOKEN=<jeton d'administration> CI_REPO=groupe/projet scripts/vault-setup.sh
#
# Variables : VAULT_ADDR, VAULT_TOKEN (racine au premier passage, puis à révoquer),
#   CI_REPO (groupe/projet), CI_BRANCH (main par défaut),
#   CI_ISSUER (https://gitlab.com par défaut ; GitLab autohébergé : son adresse),
#   CI_AUDIENCE (VAULT_ADDR par défaut : l'audience que la CI demande)
set -euo pipefail
command -v jq >/dev/null || { echo "Outil manquant : jq" >&2; exit 3; }
: "${VAULT_ADDR:?VAULT_ADDR manquant}"
: "${VAULT_TOKEN:?VAULT_TOKEN manquant : jeton administrateur}"
: "${CI_REPO:?CI_REPO manquant (groupe/projet)}"
api() {  # api MÉTHODE CHEMIN [JSON] : corps de la réponse ; l'erreur du coffre sur la sortie d'erreur
  local out code
  out="$(curl -sS -X "$1" -H "X-Vault-Token: $VAULT_TOKEN" ${3:+-H "Content-Type: application/json" -d "$3"} \
    -w '\n%{http_code}' "$VAULT_ADDR/v1/$2")" || return 1
  code="${out##*$'\n'}"
  out="${out%$'\n'*}"
  if [ "$code" -ge 300 ]; then
    echo "$1 $2 : HTTP $code $out" >&2
    return 1
  fi
  printf '%s' "$out"
}
enabled() {  # enabled sys/mounts|sys/auth CHEMIN : déjà activé ?
  api GET "$1" | jq -e --arg p "$2/" '(.data // .) | has($p)' >/dev/null
}
policy() {  # policy NOM PRÉFIXE… : lecture de <moteur>/data/<préfixe>/*
  local name="$1" rules=""
  shift
  for prefix in "$@"; do
    rules+="path \"apps/data/$prefix/*\" { capabilities = [\"read\"] }"$'\n'
  done
  api PUT "sys/policies/acl/$name" "$(jq -n --arg p "$rules" '{policy: $p}')" >/dev/null
  echo "Politique $name : lecture de apps/data/<préfixe>/* ($*)"
}

api GET auth/token/lookup-self >/dev/null || { echo "VAULT_TOKEN refusé par $VAULT_ADDR" >&2; exit 1; }
if enabled sys/mounts "apps"; then
  echo "Moteur apps déjà activé"
else
  api POST "sys/mounts/apps" '{"type": "kv", "options": {"version": "2"}}' >/dev/null
  echo "Moteur KV v2 apps activé"
fi

# Connexion de la CI (GitLab) : jeton OIDC du job, limité au dépôt et à la branche protégée
policy "mon-app-ci-read" mon-app mon-app-staging
ISSUER="${CI_ISSUER:-https://gitlab.com}"
if ! enabled sys/auth jwt; then
  api POST sys/auth/jwt '{"type": "jwt"}' >/dev/null
  echo "Méthode auth/jwt activée"
fi
api POST auth/jwt/config "$(jq -n --arg i "$ISSUER" '{oidc_discovery_url: $i, bound_issuer: $i}')" >/dev/null
api POST auth/jwt/role/mon-app-ci "$(jq -n --arg aud "${CI_AUDIENCE:-$VAULT_ADDR}" --arg repo "$CI_REPO" \
  --arg branch "${CI_BRANCH:-main}" '{
    role_type: "jwt", user_claim: "sub", bound_audiences: [$aud],
    bound_claims_type: "string", bound_claims: {project_path: $repo, ref_type: "branch", ref: $branch, ref_protected: "true"},
    token_policies: ["mon-app-ci-read"], token_ttl: "15m", token_max_ttl: "30m"}')" >/dev/null
echo "Rôle auth/jwt/role/mon-app-ci : $CI_REPO, branche ${CI_BRANCH:-main}, émetteur $ISSUER"

echo "Configuration terminée. Écrire ensuite les secrets : scripts/secrets-seed.sh <environnement>"
