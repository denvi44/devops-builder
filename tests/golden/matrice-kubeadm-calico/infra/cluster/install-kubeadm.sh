#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Initialise le plan de contrôle avec kubeadm.
set -euo pipefail

# Prérequis sur chaque nœud : containerd, kubeadm, kubelet et kubectl installés, swap désactivé.
kubeadm init --pod-network-cidr=192.168.0.0/16
mkdir -p "$HOME/.kube"
cp /etc/kubernetes/admin.conf "$HOME/.kube/config"
# Nœuds supplémentaires : kubeadm token create --print-join-command
# Les nœuds restent NotReady tant que Calico n'est pas installé.

# Ensuite, depuis un poste ayant accès au cluster :
#   bash platform/install.sh
