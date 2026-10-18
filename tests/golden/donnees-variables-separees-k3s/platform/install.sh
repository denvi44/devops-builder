#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add traefik https://traefik.github.io/charts
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true --wait

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace --set ingress.enabled=true --set ingress.ingressClassName=traefik --set 'ingress.hosts[0]=grafana.example.com' --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=grafana-tls' --set 'ingress.tls[0].hosts[0]=grafana.example.com'

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# Traefik
helm upgrade --install traefik traefik/traefik --namespace traefik --create-namespace

# ClusterIssuer Let's Encrypt (HTTPS de l'entrée, cert-manager)
kubectl apply -f "$(dirname "$0")/cluster-issuer.yaml"
