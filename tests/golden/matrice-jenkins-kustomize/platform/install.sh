#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add harbor https://helm.goharbor.io
helm repo add jenkins https://charts.jenkins.io
helm repo add sonarqube https://SonarSource.github.io/helm-chart-sonarqube
helm repo update

# Harbor
helm upgrade --install harbor harbor/harbor --namespace harbor --create-namespace

# Jenkins
helm upgrade --install jenkins jenkins/jenkins --namespace jenkins --create-namespace --set controller.ingress.enabled=true --set controller.ingress.ingressClassName=traefik --set controller.ingress.hostName=jenkins.example.com

# SonarQube — PostgreSQL externe requis en production.
kubectl create namespace sonarqube --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sonarqube get secret sonarqube-monitoring >/dev/null 2>&1 || kubectl -n sonarqube create secret generic sonarqube-monitoring --from-literal=passcode="$(openssl rand -hex 16)"
helm upgrade --install sonarqube sonarqube/sonarqube --namespace sonarqube --create-namespace --set community.enabled=true --set monitoringPasscodeSecretName=sonarqube-monitoring --set monitoringPasscodeSecretKey=passcode --set ingress.enabled=true --set 'ingress.hosts[0].name=sonarqube.example.com' --set ingress.ingressClassName=traefik
