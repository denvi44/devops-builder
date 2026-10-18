#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add dex https://charts.dexidp.io
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add harbor https://helm.goharbor.io
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add sonarqube https://SonarSource.github.io/helm-chart-sonarqube
helm repo add traefik https://traefik.github.io/charts
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
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace -f "$(dirname "$0")/values/grafana.yaml" --set ingress.enabled=true --set ingress.ingressClassName=traefik --set 'ingress.hosts[0]=grafana.boutique.fr'

# Harbor
HARBOR_OIDC_SECRET="${HARBOR_OIDC_SECRET:-}"
[ -n "${HARBOR_OIDC_SECRET:-}" ] || echo "HARBOR_OIDC_SECRET vide : connexion OIDC inactive, renseigner HARBOR_OIDC_SECRET (secret du client harbor dans Dex)" >&2
HARBOR_OIDC_ARGS=()
if [ -n "${HARBOR_OIDC_SECRET:-}" ]; then
  HARBOR_SETTINGS="$(mktemp)"
  printf '{"auth_mode":"oidc_auth","oidc_name":"Dex","oidc_endpoint":"https://dex.boutique.fr","oidc_client_id":"harbor","oidc_client_secret":"%s","oidc_scope":"openid,profile,email,groups,offline_access","oidc_groups_claim":"groups","oidc_admin_group":"admins","oidc_user_claim":"preferred_username","oidc_auto_onboard":"true","oidc_verify_cert":"true"}' "$HARBOR_OIDC_SECRET" > "$HARBOR_SETTINGS"
  HARBOR_OIDC_ARGS=(--set-file core.configureUserSettings="$HARBOR_SETTINGS")
fi
helm upgrade --install harbor harbor/harbor --namespace harbor --create-namespace --set externalURL=https://harbor.boutique.fr --set expose.ingress.hosts.core=harbor.boutique.fr --set expose.ingress.className=traefik "${HARBOR_OIDC_ARGS[@]}"

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# SonarQube — PostgreSQL externe requis en production.
kubectl create namespace sonarqube --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sonarqube get secret sonarqube-monitoring >/dev/null 2>&1 || kubectl -n sonarqube create secret generic sonarqube-monitoring --from-literal=passcode="$(openssl rand -hex 16)"
helm upgrade --install sonarqube sonarqube/sonarqube --namespace sonarqube --create-namespace --set community.enabled=true --set monitoringPasscodeSecretName=sonarqube-monitoring --set monitoringPasscodeSecretKey=passcode --set ingress.enabled=true --set 'ingress.hosts[0].name=sonarqube.boutique.fr' --set ingress.ingressClassName=traefik

# Traefik
helm upgrade --install traefik traefik/traefik --namespace traefik --create-namespace
