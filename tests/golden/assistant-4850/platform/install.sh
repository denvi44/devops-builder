#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add gitea-charts https://dl.gitea.com/charts/
helm repo add sonarqube https://SonarSource.github.io/helm-chart-sonarqube
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

# Gitea
helm upgrade --install gitea gitea-charts/gitea --namespace gitea --create-namespace

# SonarQube — PostgreSQL externe requis en production.
kubectl create namespace sonarqube --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sonarqube get secret sonarqube-monitoring >/dev/null 2>&1 || kubectl -n sonarqube create secret generic sonarqube-monitoring --from-literal=passcode="$(openssl rand -hex 16)"
helm upgrade --install sonarqube sonarqube/sonarqube --namespace sonarqube --create-namespace --set community.enabled=true --set monitoringPasscodeSecretName=sonarqube-monitoring --set monitoringPasscodeSecretKey=passcode
