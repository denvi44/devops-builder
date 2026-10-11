#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Configure Vault pour boutique, sans rien supprimer ; relançable sans risque :
#   moteur KV v2 « secret », politique de lecture boutique-ci-read,
#   connexion JWT de la CI (GitHub Actions, rôle « boutique-deploy »)
#
#   VAULT_ADDR=https://… VAULT_TOKEN=<jeton d'administration> CI_REPO=propriétaire/dépôt scripts/vault-setup.sh
#
# Variables : VAULT_ADDR, VAULT_TOKEN (racine au premier passage, puis à révoquer),
#   CI_REPO (propriétaire/dépôt), CI_BRANCH (main par défaut),
#   CI_ISSUER (https://token.actions.githubusercontent.com par défaut),
#   CI_AUDIENCE (VAULT_ADDR par défaut : l'audience que la CI demande)
set -euo pipefail
command -v jq >/dev/null || { echo "Outil manquant : jq" >&2; exit 3; }
: "${VAULT_ADDR:?VAULT_ADDR manquant}"
: "${VAULT_TOKEN:?VAULT_TOKEN manquant : jeton administrateur}"
: "${CI_REPO:?CI_REPO manquant (propriétaire/dépôt)}"
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
    rules+="path \"secret/data/$prefix/*\" { capabilities = [\"read\"] }"$'\n'
  done
  api PUT "sys/policies/acl/$name" "$(jq -n --arg p "$rules" '{policy: $p}')" >/dev/null
  echo "Politique $name : lecture de secret/data/<préfixe>/* ($*)"
}

api GET auth/token/lookup-self >/dev/null || { echo "VAULT_TOKEN refusé par $VAULT_ADDR" >&2; exit 1; }
if enabled sys/mounts "secret"; then
  echo "Moteur secret déjà activé"
else
  api POST "sys/mounts/secret" '{"type": "kv", "options": {"version": "2"}}' >/dev/null
  echo "Moteur KV v2 secret activé"
fi

# Connexion de la CI (GitHub Actions) : jeton OIDC du job, limité au dépôt et à la branche
policy "boutique-ci-read" boutique
ISSUER="${CI_ISSUER:-https://token.actions.githubusercontent.com}"
if ! enabled sys/auth jwt; then
  api POST sys/auth/jwt '{"type": "jwt"}' >/dev/null
  echo "Méthode auth/jwt activée"
fi
api POST auth/jwt/config "$(jq -n --arg i "$ISSUER" '{oidc_discovery_url: $i, bound_issuer: $i}')" >/dev/null
api POST auth/jwt/role/boutique-deploy "$(jq -n --arg aud "${CI_AUDIENCE:-$VAULT_ADDR}" --arg repo "$CI_REPO" \
  --arg branch "${CI_BRANCH:-main}" '{
    role_type: "jwt", user_claim: "sub", bound_audiences: [$aud],
    bound_claims_type: "string", bound_claims: {repository: $repo, ref: ("refs/heads/" + $branch)},
    token_policies: ["boutique-ci-read"], token_ttl: "15m", token_max_ttl: "30m"}')" >/dev/null
echo "Rôle auth/jwt/role/boutique-deploy : $CI_REPO, branche ${CI_BRANCH:-main}, émetteur $ISSUER"

echo "Configuration terminée. Écrire ensuite les secrets : scripts/secrets-seed.sh <environnement>"
