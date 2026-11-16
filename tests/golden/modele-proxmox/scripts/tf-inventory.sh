#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Inventaire Ansible d'un environnement à partir de la sortie Terraform « hosts » (machines créées par
# infra/terraform). Lancé par la CI avant chaque déploiement ; en local, après un apply.
#
#   scripts/tf-inventory.sh <environnement>          écrit l'inventaire de l'environnement
#   scripts/tf-inventory.sh --first <environnement>  affiche la première adresse (déploiement SSH)
#
# Environnements : staging, production. TF=tofu|terraform (défaut : tofu). Il faut jq et l'accès à l'état distant.
# TF_DIR=<dossier>  lit la pile d'un autre dossier (par exemple celui que garde KEEP=1 scripts/tf-floci.sh apply).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_BIN="${TF:-tofu}"
MODE="write"
if [ "${1:-}" = "--first" ]; then MODE=first; shift; fi
ENV_ID="${1:?environnement attendu (staging, production)}"
case "$ENV_ID" in
  staging) GROUP=staging; INVENTORY=ansible/inventories/staging.ini ;;
  production) GROUP=production; INVENTORY=ansible/inventories/production.ini ;;
  *) echo "Environnement inconnu : $ENV_ID (attendu : staging, production)" >&2; exit 2 ;;
esac

cd "${TF_DIR:-$ROOT/infra/terraform}"
if [ ! -d .terraform ]; then "$TF_BIN" init -input=false >/dev/null; fi
mapfile -t HOSTS < <("$TF_BIN" output -json hosts | jq -r --arg g "$GROUP" '.[$g][]? // empty')
if [ "${#HOSTS[@]}" -eq 0 ]; then
  echo "Aucune machine pour « $GROUP » dans les sorties Terraform : lancer d'abord l'apply de la pile." >&2
  exit 1
fi
if [ "$MODE" = first ]; then
  printf '%s\n' "${HOSTS[0]}"
  exit 0
fi
{
  echo "# Généré par DevOps Builder — à relire avant usage."
  echo "# Écrit par scripts/tf-inventory.sh à partir des sorties Terraform (groupe « $GROUP »)."
  echo "[app]"
  printf '%s\n' "${HOSTS[@]}"
  echo
  echo "[all:vars]"
  echo "ansible_user=deploy"
  echo "deploy_env=$ENV_ID"
} > "$ROOT/$INVENTORY"
echo "Inventaire $INVENTORY : ${#HOSTS[@]} machine(s)."
