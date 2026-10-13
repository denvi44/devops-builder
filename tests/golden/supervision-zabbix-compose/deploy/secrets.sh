#!/bin/sh
# Généré par DevOps Builder — à relire avant usage.
# Écrit les fichiers de secrets lus par Docker Compose (env_file) à partir des variables
# d'environnement ; appelé par la CI avant chaque déploiement, ou à la main sur un poste :
#   POSTGRESQL_PASSWORD=… ZABBIX_DB_PASSWORD=… sh deploy/secrets.sh deploy/secrets
set -eu
dir="${1:-secrets}"
umask 077
mkdir -p "$dir"

: "${POSTGRESQL_PASSWORD:?variable POSTGRESQL_PASSWORD manquante}"
: "${ZABBIX_DB_PASSWORD:?variable ZABBIX_DB_PASSWORD manquante}"
case "$POSTGRESQL_PASSWORD" in *[!A-Za-z0-9._~-]*)
  echo "POSTGRESQL_PASSWORD : caractères autorisés A-Za-z0-9._~- (le mot de passe entre dans une URL)" >&2
  exit 1 ;;
esac

cat > "$dir/postgresql.env" <<EOF
POSTGRES_PASSWORD=$POSTGRESQL_PASSWORD
EOF
cat > "$dir/zabbix.env" <<EOF
POSTGRES_PASSWORD=$ZABBIX_DB_PASSWORD
EOF
cat > "$dir/app.env" <<EOF
DATABASE_URL=postgresql://app:$POSTGRESQL_PASSWORD@postgresql:5432/app
EOF
echo "Secrets écrits dans $dir"
