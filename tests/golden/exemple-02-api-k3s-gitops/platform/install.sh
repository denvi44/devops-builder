#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add cilium https://helm.cilium.io/
helm repo add jetstack https://charts.jetstack.io
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add external-secrets https://charts.external-secrets.io
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo add openbao https://openbao.github.io/openbao-helm
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Cilium — À installer avant toute charge applicative (CNI).
helm upgrade --install cilium cilium/cilium --namespace kube-system --create-namespace

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

# Argo CD
helm upgrade --install argo-cd argo/argo-cd --namespace argocd --create-namespace --set configs.params.server.insecure=true

# Envoy Gateway
helm upgrade --install envoy-gateway oci://docker.io/envoyproxy/gateway-helm --namespace envoy-gateway-system --create-namespace

# External Secrets Operator
helm upgrade --install external-secrets external-secrets/external-secrets --namespace external-secrets --create-namespace --wait
kubectl apply -f "$(dirname "$0")/external-secrets/cluster-secret-store.yaml"

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace

# Kyverno
helm upgrade --install kyverno kyverno/kyverno --namespace kyverno --create-namespace

# OpenBao
helm upgrade --install openbao openbao/openbao --namespace openbao --create-namespace

# OpenTelemetry Collector
helm upgrade --install otel-collector open-telemetry/opentelemetry-collector --namespace observability --create-namespace --set mode=deployment --set image.repository=otel/opentelemetry-collector-k8s

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# Grafana Tempo
helm upgrade --install tempo grafana-community/tempo --namespace monitoring --create-namespace

# Gateway API : GatewayClass, Gateway et routes (Envoy Gateway)
kubectl apply -f "$(dirname "$0")/gateway.yaml"
