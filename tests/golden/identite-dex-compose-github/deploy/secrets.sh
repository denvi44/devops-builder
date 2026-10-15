#!/bin/sh
# Généré par DevOps Builder — à relire avant usage.
# Écrit les fichiers de secrets lus par Docker Compose (env_file) à partir des variables
# d'environnement ; appelé par la CI avant chaque déploiement, ou à la main sur un poste :
#   DEX_CONNECTOR_ID=… DEX_CONNECTOR_SECRET=… GRAFANA_OIDC_SECRET=… sh deploy/secrets.sh deploy/secrets
set -eu
dir="${1:-secrets}"
umask 077
mkdir -p "$dir"

: "${DEX_CONNECTOR_ID:?variable DEX_CONNECTOR_ID manquante}"
: "${DEX_CONNECTOR_SECRET:?variable DEX_CONNECTOR_SECRET manquante}"
: "${GRAFANA_OIDC_SECRET:?variable GRAFANA_OIDC_SECRET manquante}"

cat > "$dir/dex.env" <<EOF
DEX_CONNECTOR_ID=$DEX_CONNECTOR_ID
DEX_CONNECTOR_SECRET=$DEX_CONNECTOR_SECRET
GRAFANA_OIDC_SECRET=$GRAFANA_OIDC_SECRET
EOF
cat > "$dir/grafana.env" <<EOF
GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET=$GRAFANA_OIDC_SECRET
EOF
echo "Secrets écrits dans $dir"
