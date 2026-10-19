#!/bin/sh
# Généré par DevOps Builder — à relire avant usage.
# Écrit les fichiers de secrets lus par Docker Compose (env_file) à partir des variables
# d'environnement ; appelé par la CI avant chaque déploiement, ou à la main sur un poste :
#   GITEA_DB_PASSWORD=… GITEA_EQUIPE_B_DB_PASSWORD=… SONARQUBE_DB_PASSWORD=… GRAFANA_DB_PASSWORD=… sh deploy/secrets.sh deploy/secrets
set -eu
dir="${1:-secrets}"
umask 077
mkdir -p "$dir"

: "${GITEA_DB_PASSWORD:?variable GITEA_DB_PASSWORD manquante}"
: "${GITEA_EQUIPE_B_DB_PASSWORD:?variable GITEA_EQUIPE_B_DB_PASSWORD manquante}"
: "${SONARQUBE_DB_PASSWORD:?variable SONARQUBE_DB_PASSWORD manquante}"
: "${GRAFANA_DB_PASSWORD:?variable GRAFANA_DB_PASSWORD manquante}"

cat > "$dir/gitea-db.env" <<EOF
POSTGRES_PASSWORD=$GITEA_DB_PASSWORD
EOF
cat > "$dir/gitea.env" <<EOF
GITEA__database__PASSWD=$GITEA_DB_PASSWORD
EOF
cat > "$dir/gitea-equipe-b-db.env" <<EOF
POSTGRES_PASSWORD=$GITEA_EQUIPE_B_DB_PASSWORD
EOF
cat > "$dir/gitea-equipe-b.env" <<EOF
GITEA__database__PASSWD=$GITEA_EQUIPE_B_DB_PASSWORD
EOF
cat > "$dir/sonarqube-db.env" <<EOF
POSTGRES_PASSWORD=$SONARQUBE_DB_PASSWORD
EOF
cat > "$dir/sonarqube.env" <<EOF
SONAR_JDBC_PASSWORD=$SONARQUBE_DB_PASSWORD
EOF
cat > "$dir/grafana-db.env" <<EOF
POSTGRES_PASSWORD=$GRAFANA_DB_PASSWORD
EOF
cat > "$dir/grafana.env" <<EOF
GF_DATABASE_PASSWORD=$GRAFANA_DB_PASSWORD
EOF
echo "Secrets écrits dans $dir"
