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
helm upgrade --install jenkins jenkins/jenkins --namespace jenkins --create-namespace

# SonarQube — PostgreSQL externe requis en production.
helm upgrade --install sonarqube sonarqube/sonarqube --namespace sonarqube --create-namespace
