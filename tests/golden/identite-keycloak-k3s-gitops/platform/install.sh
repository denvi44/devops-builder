#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add external-secrets https://charts.external-secrets.io
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add openbao https://openbao.github.io/openbao-helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add traefik https://traefik.github.io/charts
helm repo update

# Keycloak — opérateur officiel, puis l'instance et sa base
kubectl create namespace keycloak --dry-run=client -o yaml | kubectl apply -f -
if ! kubectl -n keycloak get secret keycloak-db >/dev/null 2>&1; then  # mot de passe tiré une fois
  kubectl -n keycloak create secret generic keycloak-db --from-literal=username=keycloak --from-literal=password="$(openssl rand -hex 24)"
fi
kubectl apply -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/26.8.0/kubernetes/keycloaks.k8s.keycloak.org-v1.yml
kubectl apply -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/26.8.0/kubernetes/keycloakrealmimports.k8s.keycloak.org-v1.yml
kubectl apply -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/26.8.0/kubernetes/keycloakoidcclients.k8s.keycloak.org-v1.yml
kubectl apply -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/26.8.0/kubernetes/keycloaksamlclients.k8s.keycloak.org-v1.yml
kubectl -n keycloak apply -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/26.8.0/kubernetes/kubernetes.yml
kubectl -n keycloak rollout status deployment/keycloak-operator --timeout=300s
kubectl apply -f "$(dirname "$0")/keycloak/keycloak.yaml"

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

# Argo CD
ARGO_CD_OIDC_SECRET="${ARGO_CD_OIDC_SECRET:-$(tofu -chdir="$(dirname "$0")/../infra/keycloak" output -raw argo_cd_client_secret 2>/dev/null || true)}"
[ -n "${ARGO_CD_OIDC_SECRET:-}" ] || echo "ARGO_CD_OIDC_SECRET vide : connexion OIDC inactive, relancer ce script après « infra/keycloak » appliqué (docs/mise-en-route.md)" >&2
helm upgrade --install argo-cd argo/argo-cd --namespace argocd --create-namespace -f "$(dirname "$0")/values/argo-cd.yaml" --set-string "configs.secret.extra.oidc\.clientSecret=$ARGO_CD_OIDC_SECRET"

# External Secrets Operator
helm upgrade --install external-secrets external-secrets/external-secrets --namespace external-secrets --create-namespace --wait
kubectl apply -f "$(dirname "$0")/external-secrets/cluster-secret-store.yaml"

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
GRAFANA_OIDC_SECRET="${GRAFANA_OIDC_SECRET:-$(tofu -chdir="$(dirname "$0")/../infra/keycloak" output -raw grafana_client_secret 2>/dev/null || true)}"
[ -n "${GRAFANA_OIDC_SECRET:-}" ] || echo "GRAFANA_OIDC_SECRET vide : connexion OIDC inactive, relancer ce script après « infra/keycloak » appliqué (docs/mise-en-route.md)" >&2
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl -n monitoring create secret generic grafana-oidc --from-literal=GRAFANA_OIDC_SECRET="$GRAFANA_OIDC_SECRET" --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace -f "$(dirname "$0")/values/grafana.yaml"

# OpenBao
helm upgrade --install openbao openbao/openbao --namespace openbao --create-namespace

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# Traefik
helm upgrade --install traefik traefik/traefik --namespace traefik --create-namespace
