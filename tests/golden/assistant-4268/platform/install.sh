#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add gitea-charts https://dl.gitea.com/charts/
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add harbor https://helm.goharbor.io
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add sonarqube https://SonarSource.github.io/helm-chart-sonarqube
helm repo add traefik https://traefik.github.io/charts
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true --wait

# Argo CD
helm upgrade --install argo-cd argo/argo-cd --namespace argocd --create-namespace --set server.ingress.enabled=true --set server.ingress.ingressClassName=traefik --set server.ingress.hostname=argocd.example.com --set configs.params.server.insecure=true --set server.ingress.tls=true --set 'server.ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt'

# Gitea
helm upgrade --install gitea gitea-charts/gitea --namespace gitea --create-namespace --set ingress.enabled=true --set ingress.className=traefik --set 'ingress.hosts[0].host=gitea.example.com' --set 'ingress.hosts[0].paths[0].path=/' --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=gitea-tls' --set 'ingress.tls[0].hosts[0]=gitea.example.com'

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace --set ingress.enabled=true --set ingress.ingressClassName=traefik --set 'ingress.hosts[0]=grafana.example.com' --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=grafana-tls' --set 'ingress.tls[0].hosts[0]=grafana.example.com'

# Harbor
helm upgrade --install harbor harbor/harbor --namespace harbor --create-namespace --set externalURL=https://harbor.example.com --set expose.ingress.hosts.core=harbor.example.com --set expose.ingress.className=traefik --set 'expose.ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set expose.tls.certSource=secret --set expose.tls.secret.secretName=harbor-tls

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# SonarQube — PostgreSQL externe requis en production.
kubectl create namespace sonarqube --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sonarqube get secret sonarqube-monitoring >/dev/null 2>&1 || kubectl -n sonarqube create secret generic sonarqube-monitoring --from-literal=passcode="$(openssl rand -hex 16)"
helm upgrade --install sonarqube sonarqube/sonarqube --namespace sonarqube --create-namespace --set community.enabled=true --set monitoringPasscodeSecretName=sonarqube-monitoring --set monitoringPasscodeSecretKey=passcode --set ingress.enabled=true --set 'ingress.hosts[0].name=sonarqube.example.com' --set ingress.ingressClassName=traefik --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=sonarqube-tls' --set 'ingress.tls[0].hosts[0]=sonarqube.example.com'

# Traefik
helm upgrade --install traefik traefik/traefik --namespace traefik --create-namespace

# ClusterIssuer Let's Encrypt (HTTPS de l'entrée, cert-manager)
kubectl apply -f "$(dirname "$0")/cluster-issuer.yaml"
