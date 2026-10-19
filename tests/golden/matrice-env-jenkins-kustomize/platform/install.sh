#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add harbor https://helm.goharbor.io
helm repo add jenkins https://charts.jenkins.io
helm repo update

# Harbor
helm upgrade --install harbor harbor/harbor --namespace harbor --create-namespace --set externalURL=https://harbor.example.com --set expose.ingress.hosts.core=harbor.example.com --set expose.ingress.className=traefik

# Jenkins
helm upgrade --install jenkins jenkins/jenkins --namespace jenkins --create-namespace --set controller.ingress.enabled=true --set controller.ingress.ingressClassName=traefik --set controller.ingress.hostName=jenkins.example.com
