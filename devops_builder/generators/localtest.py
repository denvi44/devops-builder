# SPDX-License-Identifier: Apache-2.0
"""Test de déploiement local : un cluster kind jetable reçoit le chart Helm ou l'overlay Kustomize."""

from __future__ import annotations

import shlex

from ..ir import IR
from .common import HEADER

KIND_TEST = "scripts/test-kind.sh"

_TEMPLATE = r"""#!/usr/bin/env bash
# @HEADER@
# Test de déploiement dans un cluster kind jetable, sans toucher aux environnements réels.
#
#   scripts/test-kind.sh [environnement]        environnements : @ENVS@ (défaut : @DEFAULT@)
#
# Variables facultatives :
#   APP_DIR=chemin        dossier du code contenant le Dockerfile (défaut : racine du dépôt)
#   IMAGE=nom:tag         image déjà construite à tester, au lieu de la construire
#   KEEP_CLUSTER=1        garder le cluster après le test (kind delete cluster --name @CLUSTER@)
#   KIND_NODE_IMAGE=...   image de nœud kind (version de Kubernetes)
#   LOCAL_PORT=18080      port local utilisé pour interroger l'application
#
# Sans Dockerfile ni IMAGE, les manifestes sont envoyés à l'API du cluster en dry-run
# serveur : leur validité est vérifiée, mais l'application n'est pas démarrée.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP=@APP@
ENV_ID="${1:-@DEFAULT@}"
CLUSTER="${KIND_CLUSTER:-@CLUSTER@}"
APP_DIR="${APP_DIR:-$ROOT}"
LOCAL_PORT="${LOCAL_PORT:-18080}"
CTX="kind-$CLUSTER"

case "$ENV_ID" in
@CASES@
  *) echo "Environnement inconnu : $ENV_ID (attendu : @ENVS@)" >&2; exit 2 ;;
esac

step() { printf '\n==> %s\n' "$*"; }
need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Outil manquant : $1 — $2" >&2; exit 3; }
}
need docker "https://docs.docker.com/get-docker/"
need kind "https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
need kubectl "https://kubernetes.io/docs/tasks/tools/"
@NEED_HELM@
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
@DB_SETUP@
@DEPLOY@

if [ "$MODE" = dry-run ]; then
  step "Manifestes acceptés par l'API Kubernetes (dry-run serveur)."
  exit 0
fi

step "Attente du déploiement"
if ! kubectl --context "$CTX" -n "$NAMESPACE" rollout status "deployment/$APP" --timeout=@TIMEOUT@; then
  echo "Le déploiement n'a pas abouti. Événements récents :" >&2
  kubectl --context "$CTX" -n "$NAMESPACE" get events --sort-by=.lastTimestamp | tail -n 15 >&2 || true
  exit 1
fi

step "Vérification de la réponse HTTP (port @PORT@ du conteneur)"
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
"""

_HELM = r"""CHART="$ROOT/charts/$APP"
VALUES=(-f "$CHART/values.yaml")
if [ -f "$CHART/values-$ENV_ID.yaml" ]; then VALUES+=(-f "$CHART/values-$ENV_ID.yaml"); fi
if [ "$MODE" = deploy ]; then
  step "Installation du chart Helm"
  helm --kube-context "$CTX" upgrade --install "$APP" "$CHART" -n "$NAMESPACE" "${VALUES[@]}" \
    --set image.repository="${IMAGE%:*}" --set image.tag="${IMAGE##*:}" \
    --set image.pullPolicy=IfNotPresent --set replicaCount=1@HELM_DB@
else
  step "Rendu du chart Helm et dry-run serveur"
  helm template "$APP" "$CHART" -n "$NAMESPACE" "${VALUES[@]}"@HELM_DB@ \
    | kubectl --context "$CTX" -n "$NAMESPACE" apply --dry-run=server -f -
fi"""

_KUSTOMIZE = r"""OVERLAY="$ROOT/@OVERLAYS@/$ENV_ID"
render() {
  if command -v kustomize >/dev/null 2>&1; then kustomize build "$OVERLAY"; else kubectl kustomize "$OVERLAY"; fi
}
if [ "$MODE" = deploy ]; then
  step "Application de l'overlay Kustomize"
  render | kubectl --context "$CTX" apply -f -
  kubectl --context "$CTX" -n "$NAMESPACE" set image "deployment/$APP" "$APP=$IMAGE"
else
  step "Rendu de l'overlay Kustomize et dry-run serveur"
  render | kubectl --context "$CTX" apply --dry-run=server -f -
fi"""


_CNPG = r"""
step "Installation de l'opérateur CloudNativePG"
helm repo add cnpg https://cloudnative-pg.github.io/charts >/dev/null 2>&1 || true
helm repo update cnpg >/dev/null
helm --kube-context "$CTX" upgrade --install cnpg cnpg/cloudnative-pg -n cnpg-system --create-namespace --wait
"""


def _databases(ir: IR, helm: bool) -> tuple[str, str, bool]:
    """Préparation des bases pour kind : opérateur, mots de passe de test, URL des bases managées."""
    from . import data
    dbs = data.kube_dbs(ir)
    if not dbs:
        return "", "", False
    setup = _CNPG if any(d.mode == "operator" for d in dbs) else ""
    flags: list[str] = []
    for db in dbs:
        k = db.id.replace("-", "_")
        if db.mode == "operator":
            if helm:
                flags.append(f"--set database.{k}.instances=1")
            continue
        if db.mode == "self-hosted":
            value, field = "kindtest", "password"
            url = db.url(f"{ir.app}-{db.id}", value)
        else:
            value, field = '"${KIND_' + db.url_ci_var + ':-' + db.url("127.0.0.1", "kindtest") + '}"', "url"
            url = value
        if helm:
            flags.append(f"--set database.{k}.createSecret=true --set-string database.{k}.{field}={value}")
        else:
            lits = (f"--from-literal=password={value} --from-literal=url={url}" if db.mode == "self-hosted"
                    else f"--from-literal=url={value}")
            setup += (f'kubectl --context "$CTX" -n "$NAMESPACE" create secret generic {ir.app}-{db.id} {lits} '
                      '--dry-run=client -o yaml | kubectl --context "$CTX" apply -f - >/dev/null\n')
    helm_db = "".join(f" \\\n    {f}" for f in flags)
    if any(d.mode == "managed" for d in dbs):
        setup = ("# Base managée : non joignable depuis kind ; KIND_<VARIABLE> désigne une base de test.\n" + setup)
    return setup, helm_db, True


def kind_test(ir: IR, files: dict[str, str]) -> dict[str, str]:
    helm = any(f.startswith(f"charts/{ir.app}/") for f in files)
    kustomize = any(f.startswith("deploy/kustomize/overlays/") for f in files)
    if not (helm or kustomize):
        return {}
    envs = [e.id for e in ir.envs]
    if not envs:
        return {}
    default = next((e.id for k in ("dev", "sandbox") for e in ir.envs if e.kind == k), envs[0])
    cases = "\n".join(f"  {e.id}) NAMESPACE={shlex.quote(ir.namespace(e))} ;;" for e in ir.envs)
    deploy = _HELM if helm else _KUSTOMIZE.replace("@OVERLAYS@", "deploy/kustomize/overlays")
    db_setup, helm_db, with_db = _databases(ir, helm)
    text = (_TEMPLATE
            .replace("@DEPLOY@", deploy)
            .replace("@HEADER@", HEADER)
            .replace("@APP@", shlex.quote(ir.app))
            .replace("@ENVS@", ", ".join(envs))
            .replace("@DEFAULT@", default)
            .replace("@CLUSTER@", f"{ir.app}-test"[:40])
            .replace("@CASES@", cases)
            .replace("@NEED_HELM@", 'need helm "https://helm.sh/docs/intro/install/"\n'
                     if helm or "helm repo add" in db_setup else "")
            .replace("@DB_SETUP@", db_setup)
            .replace("@HELM_DB@", helm_db)
            .replace("@TIMEOUT@", "420s" if with_db else "180s")
            .replace("@PORT@", str(ir.project.app.port)))
    ir.notes.append(f"`{KIND_TEST}` déploie le pipeline dans un cluster kind jetable "
                    f"({'chart Helm' if helm else 'overlay Kustomize'}) : utile avant la première mise en production.")
    return {KIND_TEST: text}
