#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Écrit les secrets d'un environnement dans deploy/secrets/<env>.enc.env (SOPS),
# à partir des variables d'environnement du même nom ; une fois par environnement, puis à chaque rotation :
#   ZABBIX_DB_PASSWORD=… scripts/secrets-seed.sh <environnement>
# Environnements : production.
set -euo pipefail
ENV_ID="${1:?environnement attendu}"
case "$ENV_ID" in
  production) ;;
  *) echo "Environnement inconnu : $ENV_ID" >&2; exit 2 ;;
esac
: "${ZABBIX_DB_PASSWORD:?variable ZABBIX_DB_PASSWORD manquante}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."  # .sops.yaml à la racine du dépôt
FILE="deploy/secrets/$ENV_ID.enc.env"
mkdir -p deploy/secrets
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
{
  printf "%s=%s\n" ZABBIX_DB_PASSWORD "$ZABBIX_DB_PASSWORD"
} | sops encrypt --input-type dotenv --output-type dotenv --filename-override "$FILE" /dev/stdin > "$TMP"
mv "$TMP" "$FILE"
echo "Secrets chiffrés dans $FILE : à committer."
