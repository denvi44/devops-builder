#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add traefik https://traefik.github.io/charts
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

# Argo CD
helm upgrade --install argo-cd argo/argo-cd --namespace argocd --create-namespace --set server.ingress.enabled=true --set server.ingress.ingressClassName=traefik --set server.ingress.hostname=argocd.example.com --set configs.params.server.insecure=true

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace --set ingress.enabled=true --set ingress.ingressClassName=traefik --set 'ingress.hosts[0]=grafana.example.com'

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# Traefik
helm upgrade --install traefik traefik/traefik --namespace traefik --create-namespace
