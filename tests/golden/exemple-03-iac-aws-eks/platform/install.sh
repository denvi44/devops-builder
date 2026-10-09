#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add external-secrets https://charts.external-secrets.io
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add vmware-tanzu https://vmware-tanzu.github.io/helm-charts
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

# External Secrets Operator
helm upgrade --install external-secrets external-secrets/external-secrets --namespace external-secrets --create-namespace

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# Velero — Configurer le bucket et le plugin du fournisseur.
helm upgrade --install velero vmware-tanzu/velero --namespace velero --create-namespace
