#!/bin/sh
# Généré par DevOps Builder — à relire avant usage.
# Restaure une sauvegarde de db-backup.sh dans la base du projet Compose ; la base est déduite du nom
# du fichier. Le contenu actuel de la base est remplacé :
#   db-restore.sh /opt/<projet> /var/backups/<projet>/<base>-<date>.<ext> --oui
set -eu
dir="${1:?dossier du projet Compose, ex. /opt/mon-app}"
file="${2:?fichier de sauvegarde}"
[ -f "$file" ] || { echo "Fichier absent : $file" >&2; exit 1; }
project="$(basename "$dir")"
dc() { docker compose --project-directory "$dir" -p "$project" "$@"; }
case "$(basename "$file")" in
  postgresql-*) service=postgresql; cmd='pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error' ;;
  zabbix-db-*) service=zabbix-db; cmd='pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error' ;;
  *) echo "Base inconnue pour $(basename "$file") (préfixe attendu : postgresql-, zabbix-db-)" >&2; exit 2 ;;
esac
if [ "${3:-}" != "--oui" ]; then
  echo "La base $service de $project va être remplacée par $file : relancer avec --oui." >&2
  exit 1
fi
dc exec -T "$service" sh -c "$cmd" < "$file"
echo "$service restaurée depuis $file"
