#!/bin/sh
# Généré par DevOps Builder — à relire avant usage.
# Sauvegarde logique des bases du projet Compose, à planifier sur l'hôte (cron, timer systemd) :
#   db-backup.sh /opt/<projet> [/var/backups/<projet>]      KEEP_DAYS=7 par défaut
# Le nom du projet Compose est celui du dossier (docker compose -p).
set -eu
dir="${1:?dossier du projet Compose, ex. /opt/mon-app}"
project="$(basename "$dir")"
dest="${2:-/var/backups/$project}"
keep="${KEEP_DAYS:-7}"
stamp="$(date +%Y%m%d-%H%M%S)"
umask 077
mkdir -p "$dest"
dc() { docker compose --project-directory "$dir" -p "$project" "$@"; }

# PostgreSQL
dc exec -T postgresql sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$dest/postgresql-$stamp.dump"
echo "PostgreSQL → $dest/postgresql-$stamp.dump"
# Zabbix
dc exec -T zabbix-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$dest/zabbix-db-$stamp.dump"
echo "Zabbix → $dest/zabbix-db-$stamp.dump"

find "$dest" -type f -mtime +"$keep" -delete
