#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add cilium https://helm.cilium.io/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add traefik https://traefik.github.io/charts
helm repo update

# Cilium — À installer avant toute charge applicative (CNI).
helm upgrade --install cilium cilium/cilium --namespace kube-system --create-namespace

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# Traefik
helm upgrade --install traefik traefik/traefik --namespace traefik --create-namespace
