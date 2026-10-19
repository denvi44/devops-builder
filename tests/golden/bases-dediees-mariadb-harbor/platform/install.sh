#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add gitea-charts https://dl.gitea.com/charts/
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add harbor https://helm.goharbor.io
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add traefik https://traefik.github.io/charts
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true --wait

# Gitea
kubectl create namespace gitea --dry-run=client -o yaml | kubectl apply -f -
if ! kubectl -n gitea get secret gitea-db >/dev/null 2>&1; then  # mot de passe tiré une fois
  kubectl -n gitea create secret generic gitea-db --from-literal=username=gitea --from-literal=password="$(openssl rand -hex 24)"
fi
kubectl apply -f "$(dirname "$0")/db-gitea.yaml"
helm upgrade --install gitea gitea-charts/gitea --namespace gitea --create-namespace --set ingress.enabled=true --set ingress.className=traefik --set 'ingress.hosts[0].host=gitea.example.com' --set 'ingress.hosts[0].paths[0].path=/' --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=gitea-tls' --set 'ingress.tls[0].hosts[0]=gitea.example.com' --set postgresql-ha.enabled=false --set postgresql.enabled=false --set gitea.config.database.DB_TYPE=mysql --set gitea.config.database.HOST=gitea-db:3306 --set gitea.config.database.NAME=gitea --set gitea.config.database.USER=gitea --set 'gitea.additionalConfigFromEnvs[0].name=GITEA__DATABASE__PASSWD' --set 'gitea.additionalConfigFromEnvs[0].valueFrom.secretKeyRef.name=gitea-db' --set 'gitea.additionalConfigFromEnvs[0].valueFrom.secretKeyRef.key=password'

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace --set ingress.enabled=true --set ingress.ingressClassName=traefik --set 'ingress.hosts[0]=grafana.example.com' --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=grafana-tls' --set 'ingress.tls[0].hosts[0]=grafana.example.com'

# Harbor
kubectl create namespace harbor --dry-run=client -o yaml | kubectl apply -f -
if ! kubectl -n harbor get secret harbor-db >/dev/null 2>&1; then  # mot de passe tiré une fois
  kubectl -n harbor create secret generic harbor-db --from-literal=username=harbor --from-literal=password="$(openssl rand -hex 24)"
fi
kubectl apply -f "$(dirname "$0")/db-harbor.yaml"
helm upgrade --install harbor harbor/harbor --namespace harbor --create-namespace --set externalURL=https://harbor.boutique.fr --set expose.ingress.hosts.core=harbor.boutique.fr --set expose.ingress.className=traefik --set 'expose.ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set expose.tls.certSource=secret --set expose.tls.secret.secretName=harbor-tls --set database.type=external --set database.external.host=harbor-db --set database.external.port=5432 --set database.external.username=harbor --set database.external.coreDatabase=harbor --set database.external.existingSecret=harbor-db

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# Traefik
helm upgrade --install traefik traefik/traefik --namespace traefik --create-namespace

# ClusterIssuer Let's Encrypt (HTTPS de l'entrée, cert-manager)
kubectl apply -f "$(dirname "$0")/cluster-issuer.yaml"
