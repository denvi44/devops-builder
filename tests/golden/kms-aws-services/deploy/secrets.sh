#!/bin/sh
# Généré par DevOps Builder — à relire avant usage.
# Écrit les fichiers de secrets lus par Docker Compose (env_file) à partir des variables
# d'environnement ; appelé par la CI avant chaque déploiement, ou à la main sur un poste :
#   REDIS_URL=… sh deploy/secrets.sh deploy/secrets
set -eu
dir="${1:-secrets}"
umask 077
mkdir -p "$dir"

: "${REDIS_URL:?variable REDIS_URL manquante}"

cat > "$dir/app.env" <<EOF
REDIS_URL=$REDIS_URL
EOF
echo "Secrets écrits dans $dir"
