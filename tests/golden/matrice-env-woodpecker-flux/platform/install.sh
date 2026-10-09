#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add fluxcd-community https://fluxcd-community.github.io/helm-charts
helm repo add gitea-charts https://dl.gitea.com/charts/
helm repo add project-zot https://zotregistry.dev/helm-charts
helm repo update

# Flux
helm upgrade --install flux fluxcd-community/flux2 --namespace flux-system --create-namespace

# Gitea
helm upgrade --install gitea gitea-charts/gitea --namespace gitea --create-namespace

# zot
helm upgrade --install zot project-zot/zot --namespace zot --create-namespace
