#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Écrit les secrets d'un environnement dans OpenBao,
# à partir des variables d'environnement du même nom ; une fois par environnement, puis à chaque rotation :
#   MYSQL_PASSWORD=… scripts/secrets-seed.sh <environnement>
# Environnements : dev, staging, production.
set -euo pipefail
ENV_ID="${1:?environnement attendu}"
case "$ENV_ID" in
  dev) NS=mon-app-dev ;;
  staging) NS=mon-app-staging ;;
  production) NS=mon-app ;;
  *) echo "Environnement inconnu : $ENV_ID" >&2; exit 2 ;;
esac
: "${MYSQL_PASSWORD:?variable MYSQL_PASSWORD manquante}"
case "$MYSQL_PASSWORD" in *[!A-Za-z0-9._~-]*)
  echo "MYSQL_PASSWORD : caractères autorisés A-Za-z0-9._~-" >&2; exit 1 ;;
esac

curl -fsS -X POST -H "X-Vault-Token: ${VAULT_TOKEN:?VAULT_TOKEN manquant}" -d "$(jq -n --arg password "$MYSQL_PASSWORD" '{password: $password}' | jq '{data: .}')" "${VAULT_ADDR:?VAULT_ADDR manquant}/v1/secret/data/$NS/mysql" >/dev/null
echo "mysql : secret écrit pour $ENV_ID"
