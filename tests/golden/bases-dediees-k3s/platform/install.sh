#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo add gitea-charts https://dl.gitea.com/charts/
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add sonarqube https://SonarSource.github.io/helm-chart-sonarqube
helm repo add traefik https://traefik.github.io/charts
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true --wait

# CloudNativePG — Opérateur seulement : le Cluster PostgreSQL est livré avec l'application.
helm upgrade --install cloudnative-pg cnpg/cloudnative-pg --namespace cnpg-system --create-namespace

# Gitea
kubectl create namespace gitea --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$(dirname "$0")/db-gitea.yaml"
helm upgrade --install gitea gitea-charts/gitea --namespace gitea --create-namespace --set ingress.enabled=true --set ingress.className=traefik --set 'ingress.hosts[0].host=gitea.example.com' --set 'ingress.hosts[0].paths[0].path=/' --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=gitea-tls' --set 'ingress.tls[0].hosts[0]=gitea.example.com' --set postgresql-ha.enabled=false --set postgresql.enabled=false --set gitea.config.database.DB_TYPE=postgres --set gitea.config.database.HOST=gitea-pg-rw:5432 --set gitea.config.database.NAME=gitea --set gitea.config.database.USER=gitea --set 'gitea.additionalConfigFromEnvs[0].name=GITEA__DATABASE__PASSWD' --set 'gitea.additionalConfigFromEnvs[0].valueFrom.secretKeyRef.name=gitea-pg-app' --set 'gitea.additionalConfigFromEnvs[0].valueFrom.secretKeyRef.key=password'

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace --set ingress.enabled=true --set ingress.ingressClassName=traefik --set 'ingress.hosts[0]=grafana.example.com' --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=grafana-tls' --set 'ingress.tls[0].hosts[0]=grafana.example.com'

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$(dirname "$0")/db-grafana.yaml"
helm upgrade --install grafana grafana-community/grafana --namespace monitoring --create-namespace --set ingress.enabled=true --set ingress.ingressClassName=traefik --set 'ingress.hosts[0]=grafana.example.com' --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=grafana-tls' --set 'ingress.tls[0].hosts[0]=grafana.example.com' --set 'grafana\.ini.database.type=postgres' --set 'grafana\.ini.database.host=grafana-pg-rw:5432' --set 'grafana\.ini.database.name=grafana' --set 'grafana\.ini.database.user=grafana' --set 'envValueFrom.GF_DATABASE_PASSWORD.secretKeyRef.name=grafana-pg-app' --set 'envValueFrom.GF_DATABASE_PASSWORD.secretKeyRef.key=password'

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# SonarQube — PostgreSQL externe requis en production.
kubectl create namespace sonarqube --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sonarqube get secret sonarqube-monitoring >/dev/null 2>&1 || kubectl -n sonarqube create secret generic sonarqube-monitoring --from-literal=passcode="$(openssl rand -hex 16)"
kubectl create namespace sonarqube --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$(dirname "$0")/db-sonarqube.yaml"
helm upgrade --install sonarqube sonarqube/sonarqube --namespace sonarqube --create-namespace --set community.enabled=true --set monitoringPasscodeSecretName=sonarqube-monitoring --set monitoringPasscodeSecretKey=passcode --set ingress.enabled=true --set 'ingress.hosts[0].name=sonarqube.example.com' --set ingress.ingressClassName=traefik --set 'ingress.annotations.cert-manager\.io/cluster-issuer=letsencrypt' --set 'ingress.tls[0].secretName=sonarqube-tls' --set 'ingress.tls[0].hosts[0]=sonarqube.example.com' --set postgresql.enabled=false --set jdbcOverwrite.enable=true --set jdbcOverwrite.jdbcUrl=jdbc:postgresql://sonarqube-pg-rw:5432/sonarqube --set jdbcOverwrite.jdbcUsername=sonarqube --set jdbcOverwrite.jdbcSecretName=sonarqube-pg-app --set jdbcOverwrite.jdbcSecretPasswordKey=password

# Traefik
helm upgrade --install traefik traefik/traefik --namespace traefik --create-namespace

# ClusterIssuer Let's Encrypt (HTTPS de l'entrée, cert-manager)
kubectl apply -f "$(dirname "$0")/cluster-issuer.yaml"
