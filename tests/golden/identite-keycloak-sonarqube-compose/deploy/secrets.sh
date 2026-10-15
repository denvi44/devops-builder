#!/bin/sh
# Généré par DevOps Builder — à relire avant usage.
# Écrit les fichiers de secrets lus par Docker Compose (env_file) à partir des variables
# d'environnement ; appelé par la CI avant chaque déploiement, ou à la main sur un poste :
#   KEYCLOAK_DB_PASSWORD=… KEYCLOAK_ADMIN_PASSWORD=… GRAFANA_OIDC_SECRET=… sh deploy/secrets.sh deploy/secrets
set -eu
dir="${1:-secrets}"
umask 077
mkdir -p "$dir"

: "${KEYCLOAK_DB_PASSWORD:?variable KEYCLOAK_DB_PASSWORD manquante}"
: "${KEYCLOAK_ADMIN_PASSWORD:?variable KEYCLOAK_ADMIN_PASSWORD manquante}"
: "${GRAFANA_OIDC_SECRET:=}"  # facultative au premier déploiement

cat > "$dir/keycloak.env" <<EOF
KC_DB_PASSWORD=$KEYCLOAK_DB_PASSWORD
KC_BOOTSTRAP_ADMIN_PASSWORD=$KEYCLOAK_ADMIN_PASSWORD
EOF
cat > "$dir/keycloak-db.env" <<EOF
POSTGRES_PASSWORD=$KEYCLOAK_DB_PASSWORD
EOF
cat > "$dir/grafana.env" <<EOF
GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET=$GRAFANA_OIDC_SECRET
EOF
echo "Secrets écrits dans $dir"
