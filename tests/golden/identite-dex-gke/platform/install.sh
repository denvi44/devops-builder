#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add dex https://charts.dexidp.io
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

# Dex
helm upgrade --install dex dex/dex --namespace dex --create-namespace -f "$(dirname "$0")/values/dex.yaml"

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
GRAFANA_OIDC_SECRET="${GRAFANA_OIDC_SECRET:-}"
[ -n "${GRAFANA_OIDC_SECRET:-}" ] || echo "GRAFANA_OIDC_SECRET vide : connexion OIDC inactive, renseigner GRAFANA_OIDC_SECRET (secret du client grafana dans Dex)" >&2
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl -n monitoring create secret generic grafana-oidc --from-literal=GRAFANA_OIDC_SECRET="$GRAFANA_OIDC_SECRET" --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace -f "$(dirname "$0")/values/grafana.yaml"

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace
