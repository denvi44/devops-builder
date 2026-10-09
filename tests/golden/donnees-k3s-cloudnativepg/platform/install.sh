#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add traefik https://traefik.github.io/charts
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

# CloudNativePG — Opérateur seulement : le Cluster PostgreSQL est livré avec l'application.
helm upgrade --install cloudnative-pg cnpg/cloudnative-pg --namespace cnpg-system --create-namespace

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
helm upgrade --install grafana grafana/grafana --namespace monitoring --create-namespace

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# Traefik
helm upgrade --install traefik traefik/traefik --namespace traefik --create-namespace
