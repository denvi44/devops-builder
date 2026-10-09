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

# MariaDB
dc exec -T mariadb sh -c 'mariadb-dump -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" --single-transaction "$MARIADB_DATABASE"' > "$dest/mariadb-$stamp.sql"
echo "MariaDB → $dest/mariadb-$stamp.sql"

find "$dest" -type f -mtime +"$keep" -delete
