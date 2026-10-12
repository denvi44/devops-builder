#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Écrit les secrets d'un environnement dans OpenBao,
# à partir des variables d'environnement du même nom ; une fois par environnement, puis à chaque rotation :
#   GRAFANA_OIDC_SECRET=… KEYCLOAK_ADMIN_PASSWORD=… KEYCLOAK_DB_PASSWORD=… POSTGRESQL_PASSWORD=… scripts/secrets-seed.sh <environnement>
# Environnements : staging, production.
set -euo pipefail
ENV_ID="${1:?environnement attendu}"
case "$ENV_ID" in
  staging) NS=mon-app-staging ;;
  production) NS=mon-app ;;
  *) echo "Environnement inconnu : $ENV_ID" >&2; exit 2 ;;
esac
: "${GRAFANA_OIDC_SECRET:?variable GRAFANA_OIDC_SECRET manquante}"
: "${KEYCLOAK_ADMIN_PASSWORD:?variable KEYCLOAK_ADMIN_PASSWORD manquante}"
: "${KEYCLOAK_DB_PASSWORD:?variable KEYCLOAK_DB_PASSWORD manquante}"
: "${POSTGRESQL_PASSWORD:?variable POSTGRESQL_PASSWORD manquante}"
case "$POSTGRESQL_PASSWORD" in *[!A-Za-z0-9._~-]*)
  echo "POSTGRESQL_PASSWORD : caractères autorisés A-Za-z0-9._~-" >&2; exit 1 ;;
esac

curl -fsS -X POST -H "X-Vault-Token: ${VAULT_TOKEN:?VAULT_TOKEN manquant}" -d "$(jq -n --arg password "$POSTGRESQL_PASSWORD" '{password: $password}' | jq '{data: .}')" "${VAULT_ADDR:?VAULT_ADDR manquant}/v1/secret/data/$NS/postgresql" >/dev/null
echo "postgresql : secret écrit pour $ENV_ID"
curl -fsS -X POST -H "X-Vault-Token: ${VAULT_TOKEN:?VAULT_TOKEN manquant}" -d "$(jq -n --arg keycloak_db_password "$KEYCLOAK_DB_PASSWORD" --arg keycloak_admin_password "$KEYCLOAK_ADMIN_PASSWORD" --arg grafana_oidc_secret "$GRAFANA_OIDC_SECRET" '{keycloak_db_password: $keycloak_db_password, keycloak_admin_password: $keycloak_admin_password, grafana_oidc_secret: $grafana_oidc_secret}' | jq '{data: .}')" "${VAULT_ADDR:?VAULT_ADDR manquant}/v1/secret/data/$NS/keycloak" >/dev/null
echo "keycloak : secret écrit pour $ENV_ID"
