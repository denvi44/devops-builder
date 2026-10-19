#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Test de déploiement dans un cluster kind jetable, sans toucher aux environnements réels.
#
#   scripts/test-kind.sh [environnement]        environnements : staging, production (défaut : staging)
#
# Variables facultatives :
#   APP_DIR=chemin        dossier du code contenant le Dockerfile (défaut : racine du dépôt)
#   IMAGE=nom:tag         image déjà construite à tester, au lieu de la construire
#   KEEP_CLUSTER=1        garder le cluster après le test (kind delete cluster --name mon-app-test)
#   KIND_NODE_IMAGE=...   image de nœud kind (version de Kubernetes)
#   LOCAL_PORT=18080      port local utilisé pour interroger l'application
#
# Sans Dockerfile ni IMAGE, les manifestes sont envoyés à l'API du cluster en dry-run
# serveur : leur validité est vérifiée, mais l'application n'est pas démarrée.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP=mon-app
ENV_ID="${1:-staging}"
CLUSTER="${KIND_CLUSTER:-mon-app-test}"
APP_DIR="${APP_DIR:-$ROOT}"
LOCAL_PORT="${LOCAL_PORT:-18080}"
CTX="kind-$CLUSTER"

case "$ENV_ID" in
  staging) NAMESPACE=mon-app-staging ;;
  production) NAMESPACE=mon-app ;;
  *) echo "Environnement inconnu : $ENV_ID (attendu : staging, production)" >&2; exit 2 ;;
esac

step() { printf '\n==> %s\n' "$*"; }
need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Outil manquant : $1 — $2" >&2; exit 3; }
}
need docker "https://docs.docker.com/get-docker/"
need kind "https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
need kubectl "https://kubernetes.io/docs/tasks/tools/"
need helm "https://helm.sh/docs/intro/install/"

created=0
PF_PID=""
cleanup() {
  if [ -n "$PF_PID" ]; then kill "$PF_PID" 2>/dev/null || true; fi
  if [ "$created" = 1 ] && [ "${KEEP_CLUSTER:-0}" != 1 ]; then
    step "Suppression du cluster $CLUSTER"
    kind delete cluster --name "$CLUSTER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  step "Cluster kind $CLUSTER existant : réutilisé"
else
  step "Création du cluster kind $CLUSTER"
  if [ -n "${KIND_NODE_IMAGE:-}" ]; then
    kind create cluster --name "$CLUSTER" --wait 180s --image "$KIND_NODE_IMAGE"
  else
    kind create cluster --name "$CLUSTER" --wait 180s
  fi
  created=1
fi

MODE=dry-run
if [ -n "${IMAGE:-}" ]; then
  MODE=deploy
elif [ -f "$APP_DIR/Dockerfile" ]; then
  IMAGE="devops-builder.local/$APP:kind-$(date +%s)"
  step "Construction de l'image depuis $APP_DIR"
  docker build -t "$IMAGE" "$APP_DIR"
  MODE=deploy
fi
if [ "$MODE" = deploy ]; then
  step "Chargement de l'image $IMAGE dans le cluster"
  kind load docker-image "$IMAGE" --name "$CLUSTER"
else
  echo "Aucun Dockerfile dans $APP_DIR ni IMAGE fournie : dry-run serveur, l'application ne sera pas démarrée."
fi

kubectl --context "$CTX" create namespace "$NAMESPACE" --dry-run=client -o yaml \
  | kubectl --context "$CTX" apply -f - >/dev/null

step "Installation de l'opérateur CloudNativePG"
helm repo add cnpg https://cloudnative-pg.github.io/charts >/dev/null 2>&1 || true
helm repo update cnpg >/dev/null
helm --kube-context "$CTX" upgrade --install cnpg cnpg/cloudnative-pg -n cnpg-system --create-namespace --wait

CHART="$ROOT/charts/$APP"
VALUES=(-f "$CHART/values.yaml")
if [ -f "$CHART/values-$ENV_ID.yaml" ]; then VALUES+=(-f "$CHART/values-$ENV_ID.yaml"); fi
if [ "$MODE" = deploy ]; then
  step "Installation du chart Helm"
  helm --kube-context "$CTX" upgrade --install "$APP" "$CHART" -n "$NAMESPACE" "${VALUES[@]}" \
    --set image.repository="${IMAGE%:*}" --set image.tag="${IMAGE##*:}" \
    --set image.pullPolicy=IfNotPresent --set replicaCount=1 \
    --set database.cloudnative_pg.instances=1
else
  step "Rendu du chart Helm et dry-run serveur"
  helm template "$APP" "$CHART" -n "$NAMESPACE" "${VALUES[@]}" \
    --set database.cloudnative_pg.instances=1 \
    | kubectl --context "$CTX" -n "$NAMESPACE" apply --dry-run=server -f -
fi

if [ "$MODE" = dry-run ]; then
  step "Manifestes acceptés par l'API Kubernetes (dry-run serveur)."
  exit 0
fi

step "Attente du déploiement"
if ! kubectl --context "$CTX" -n "$NAMESPACE" rollout status "deployment/$APP" --timeout=420s; then
  echo "Le déploiement n'a pas abouti. Événements récents :" >&2
  kubectl --context "$CTX" -n "$NAMESPACE" get events --sort-by=.lastTimestamp | tail -n 15 >&2 || true
  exit 1
fi

step "Vérification de la réponse HTTP (port 8000 du conteneur)"
kubectl --context "$CTX" -n "$NAMESPACE" port-forward "service/$APP" "$LOCAL_PORT:80" >/dev/null 2>&1 &
PF_PID=$!
code=000
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$LOCAL_PORT/" || true)
  if [ "$code" != 000 ]; then break; fi
  sleep 1
done
if [ "$code" = 000 ]; then
  echo "L'application ne répond pas. Derniers journaux :" >&2
  kubectl --context "$CTX" -n "$NAMESPACE" logs "deployment/$APP" --tail=50 >&2 || true
  exit 1
fi
restarts=$(kubectl --context "$CTX" -n "$NAMESPACE" get pods -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}')
for r in $restarts; do
  if [ "$r" -gt 0 ]; then
    echo "Un conteneur a redémarré ($r fois) : voir kubectl logs --previous." >&2
    exit 1
  fi
done
step "Test réussi : l'application répond (HTTP $code) dans « $ENV_ID »."
