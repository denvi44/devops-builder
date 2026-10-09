#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Installe un serveur RKE2 sur ce nœud.
set -euo pipefail

mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml <<'EOF'
cni: canal
EOF
curl -sfL https://get.rke2.io | sh -
systemctl enable --now rke2-server.service
# kubeconfig : /etc/rancher/rke2/rke2.yaml

# Ensuite, depuis un poste ayant accès au cluster :
#   bash platform/install.sh
