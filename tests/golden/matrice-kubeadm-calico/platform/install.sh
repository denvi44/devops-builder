#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).
set -euo pipefail

helm repo add projectcalico https://docs.tigera.io/calico/charts
helm repo update

# Calico — À installer avant toute charge applicative (CNI).
helm upgrade --install calico projectcalico/tigera-operator --namespace tigera-operator --create-namespace
