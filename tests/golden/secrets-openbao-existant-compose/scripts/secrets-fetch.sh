#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Charge les secrets d'un environnement (source : vault) et les affiche en « export NOM=valeur » :
#   eval "$(bash scripts/secrets-fetch.sh <environnement>)"
# Environnements : staging, production. Rien n'est écrit sur le disque.
set -euo pipefail
ENV_ID="${1:?environnement attendu (staging, production)}"
case "$ENV_ID" in
  staging) NS=mon-app-staging ;;
  production) NS=mon-app ;;
  *) echo "Environnement inconnu : $ENV_ID" >&2; exit 2 ;;
esac
command -v jq >/dev/null || { echo "Outil manquant : jq" >&2; exit 3; }
: "${VAULT_ADDR:?VAULT_ADDR manquant}"
TOKEN="${VAULT_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  JWT="${VAULT_ID_TOKEN:-}"
  if [ -z "$JWT" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then  # GitHub Actions, permission id-token: write
    JWT="$(curl -fsS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
      "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=$VAULT_ADDR" | jq -r .value)"
  fi
  [ -n "$JWT" ] || { echo "Ni VAULT_TOKEN ni jeton OIDC de la CI : connexion au coffre impossible" >&2; exit 1; }
  TOKEN="$(curl -fsS -X POST -d "$(jq -n --arg r "mon-app-ci" --arg j "$JWT" '{role: $r, jwt: $j}')" \
    "$VAULT_ADDR/v1/auth/jwt/login" | jq -er .auth.client_token)" \
    || { echo "Connexion refusée par le coffre (auth/jwt, rôle mon-app-ci)" >&2; exit 1; }
fi
read_secret() {  # read_secret VARIABLE CHEMIN PROPRIÉTÉ
  local value
  value="$(curl -fsS -H "X-Vault-Token: $TOKEN" "$VAULT_ADDR/v1/apps/data/$2" | jq -er --arg p "$3" '.data.data[$p]')" \
    || { echo "Secret absent : apps/$2 ($3) — scripts/secrets-seed.sh $ENV_ID" >&2; exit 1; }
  printf 'export %s=%q\n' "$1" "$value"
}
read_secret POSTGRESQL_PASSWORD "$NS/postgresql" password

