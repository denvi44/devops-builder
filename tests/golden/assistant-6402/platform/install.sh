#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add jetstack https://charts.jetstack.io
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add sonarqube https://SonarSource.github.io/helm-chart-sonarqube
helm repo update

# cert-manager
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

# Grafana — Déjà inclus si kube-prometheus-stack est installé.
helm upgrade --install grafana grafana/grafana --namespace monitoring --create-namespace

# Prometheus
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# SonarQube — PostgreSQL externe requis en production.
helm upgrade --install sonarqube sonarqube/sonarqube --namespace sonarqube --create-namespace
