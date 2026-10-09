#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

# Argo CD
helm upgrade --install argo-cd argo/argo-cd --namespace argocd --create-namespace
