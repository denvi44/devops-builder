#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add external-secrets https://charts.external-secrets.io
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

# External Secrets Operator
ESO_CLIENT_ID="${ESO_CLIENT_ID:-$(tofu -chdir="$(dirname "$0")/../infra/terraform" output -raw eso_client_id)}"
ESO_TENANT_ID="${ESO_TENANT_ID:-$(tofu -chdir="$(dirname "$0")/../infra/terraform" output -raw eso_tenant_id)}"
helm upgrade --install external-secrets external-secrets/external-secrets --namespace external-secrets --create-namespace --set-string "serviceAccount.annotations.azure\.workload\.identity/client-id=$ESO_CLIENT_ID" --set-string "serviceAccount.annotations.azure\.workload\.identity/tenant-id=$ESO_TENANT_ID" --set-string "podLabels.azure\.workload\.identity/use=true" --wait
kubectl apply -f "$(dirname "$0")/external-secrets/cluster-secret-store.yaml"

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace
