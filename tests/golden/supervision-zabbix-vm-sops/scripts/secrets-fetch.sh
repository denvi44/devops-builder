#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Charge les secrets d'un environnement (source : sops) et les affiche en « export NOM=valeur » :
#   eval "$(bash scripts/secrets-fetch.sh <environnement>)"
# Environnements : production. Rien n'est écrit sur le disque.
set -euo pipefail
ENV_ID="${1:?environnement attendu (production)}"
case "$ENV_ID" in
  production) ;;
  *) echo "Environnement inconnu : $ENV_ID" >&2; exit 2 ;;
esac
command -v sops >/dev/null || { echo "Outil manquant : sops" >&2; exit 3; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="$ROOT/deploy/secrets/$ENV_ID.enc.env"
[ -f "$FILE" ] || { echo "Fichier absent : $FILE (scripts/secrets-seed.sh $ENV_ID le crée)" >&2; exit 1; }
sops decrypt --input-type dotenv --output-type dotenv "$FILE" | while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  printf 'export %s=%q\n' "${line%%=*}" "${line#*=}"
done

