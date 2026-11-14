#!/bin/sh
# Généré par DevOps Builder — à relire avant usage.
# Écrit les fichiers de secrets lus par Docker Compose (env_file) à partir des variables
# d'environnement ; appelé par la CI avant chaque déploiement, ou à la main sur un poste :
#   ZABBIX_DB_PASSWORD=… sh deploy/secrets.sh deploy/secrets
set -eu
dir="${1:-secrets}"
umask 077
mkdir -p "$dir"

: "${ZABBIX_DB_PASSWORD:?variable ZABBIX_DB_PASSWORD manquante}"

cat > "$dir/zabbix.env" <<EOF
POSTGRES_PASSWORD=$ZABBIX_DB_PASSWORD
EOF
echo "Secrets écrits dans $dir"
