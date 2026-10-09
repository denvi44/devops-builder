#!/bin/sh
# Généré par DevOps Builder — à relire avant usage.
# Écrit les fichiers de secrets lus par Docker Compose (env_file) à partir des variables
# d'environnement ; appelé par la CI avant chaque déploiement, ou à la main sur un poste :
#   MARIADB_PASSWORD=… sh deploy/secrets.sh deploy/secrets
set -eu
dir="${1:-secrets}"
umask 077
mkdir -p "$dir"

: "${MARIADB_PASSWORD:?variable MARIADB_PASSWORD manquante}"
case "$MARIADB_PASSWORD" in *[!A-Za-z0-9._~-]*)
  echo "MARIADB_PASSWORD : caractères autorisés A-Za-z0-9._~- (le mot de passe entre dans une URL)" >&2
  exit 1 ;;
esac

cat > "$dir/mariadb.env" <<EOF
MARIADB_PASSWORD=$MARIADB_PASSWORD
EOF
cat > "$dir/app.env" <<EOF
DATABASE_URL=mysql://app:$MARIADB_PASSWORD@mariadb:3306/app
EOF
echo "Secrets écrits dans $dir"
