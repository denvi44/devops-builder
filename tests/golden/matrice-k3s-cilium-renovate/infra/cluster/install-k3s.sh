#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe un serveur k3s sur ce nœud.
set -euo pipefail

curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --flannel-backend=none --disable-network-policy --disable traefik" sh -
# kubeconfig : /etc/rancher/k3s/k3s.yaml
# Nœuds supplémentaires : K3S_URL=https://<serveur>:6443 K3S_TOKEN=<jeton> (voir /var/lib/rancher/k3s/server/node-token)
# Flannel est désactivé : les nœuds restent NotReady tant que Cilium n'est pas installé.

# Ensuite, depuis un poste ayant accès au cluster :
#   bash platform/install.sh
