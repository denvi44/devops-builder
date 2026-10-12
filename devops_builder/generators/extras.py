# SPDX-License-Identifier: Apache-2.0
"""Fichiers complémentaires : mises à jour de dépendances et installation des clusters autogérés."""

from __future__ import annotations

import json

from ..ir import IR
from .common import HEADER, dump_yaml

INGRESS_TOOLS = ("traefik", "envoy-gateway", "ingress-nginx")
SELF_MANAGED = ("k3s", "rke2", "kubeadm", "microk8s", "kind", "minikube")
DEPENDABOT_ECOSYSTEMS = {"python": "pip", "node": "npm", "java": "maven", "go": "gomod", "dotnet": "nuget"}
DOCKERFILE_BUILDERS = ("buildkit", "buildah", "kaniko")


def _cni(ir: IR) -> str | None:
    for t in ("cilium", "calico", "flannel"):
        if ir.has(t):
            return t
    return None


def _ingress(ir: IR) -> list[str]:
    return [t for t in INGRESS_TOOLS if ir.has(t)]


# ---------------------------------------------------------------- composants embarqués
def embedded_components(ir: IR) -> dict[str, str]:
    """Briques déjà fournies par le cluster choisi : elles ne sont pas réinstallées par Helm.

    Retourne {tool_id: explication}.
    """
    out: dict[str, str] = {}
    cni = _cni(ir)
    if ir.has("k3s") and cni == "flannel":
        out["flannel"] = "Flannel est le CNI intégré de k3s : il n'est pas réinstallé."
    if ir.has("rke2") and cni:
        out[cni] = f"RKE2 installe lui-même {ir.catalog[cni].name} (clé « cni » de /etc/rancher/rke2/config.yaml)."
    if ir.has("microk8s") and cni == "calico":
        out["calico"] = "Calico est le CNI intégré de MicroK8s : il n'est pas réinstallé."
    if ir.has("minikube") and cni:
        out[cni] = f"minikube installe {ir.catalog[cni].name} au démarrage (option --cni)."
    return out


# ------------------------------------------------------------------- dépendances
def renovate(ir: IR) -> dict[str, str]:
    if not ir.has("renovate"):
        return {}
    config = {
        "$schema": "https://docs.renovatebot.com/renovate-schema.json",
        "extends": ["config:recommended"],
        "labels": ["dependencies"],
        "dependencyDashboard": True,
    }
    forge = ir.forge.id if ir.forge else None
    if forge == "github":
        ir.notes.append("Renovate : installer l'application GitHub Renovate sur le dépôt ; renovate.json règle son comportement.")
    else:
        ir.add_var("RENOVATE_TOKEN", "Jeton de la forge autorisé à ouvrir des merge requests (Renovate)")
        ir.notes.append("Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; "
                        "renovate.json règle son comportement.")
    ir.cover("renovate")
    return {"renovate.json": json.dumps(config, indent=2, ensure_ascii=False) + "\n"}


def dependabot(ir: IR) -> dict[str, str]:
    if not ir.has("dependabot"):
        return {}
    updates = []
    weekly = {"interval": "weekly"}
    eco = DEPENDABOT_ECOSYSTEMS.get(ir.project.app.language)
    if eco:
        updates.append({"package-ecosystem": eco, "directory": "/", "schedule": weekly})
    if any(ir.has(b) for b in DOCKERFILE_BUILDERS):
        updates.append({"package-ecosystem": "docker", "directory": "/", "schedule": weekly})
    if ir.ci and ir.ci.id == "github-actions":
        updates.append({"package-ecosystem": "github-actions", "directory": "/", "schedule": weekly})
    if ir.iac and ir.iac.id in ("terraform", "opentofu"):
        updates.append({"package-ecosystem": "terraform", "directory": "/infra/terraform", "schedule": weekly})
    if not updates:
        ir.notes.append("Dependabot : aucun écosystème détecté pour ce projet ; compléter .github/dependabot.yml.")
        updates.append({"package-ecosystem": "github-actions", "directory": "/", "schedule": weekly})
    ir.cover("dependabot")
    return {".github/dependabot.yml": dump_yaml({"version": 2, "updates": updates})}


# ------------------------------------------------------------------- clusters
def k3s_exec_flags(ir: IR) -> str:
    flags = ["server"]
    cni = _cni(ir)
    if cni in ("cilium", "calico"):
        flags += ["--flannel-backend=none", "--disable-network-policy"]
    if _ingress(ir):
        flags.append("--disable traefik")  # l'entrée choisie est installée par platform/install.sh
    return " ".join(flags)


def _script(title: str, body: list[str]) -> str:
    return "\n".join(["#!/usr/bin/env bash", f"# {HEADER}", f"# {title}", "set -euo pipefail", "", *body, ""])


def _platform_hint(ir: IR) -> list[str]:
    from .platform import PLATFORM_CHARTS
    if any(ir.has(t) for t in PLATFORM_CHARTS):
        return ["", "# Ensuite, depuis un poste ayant accès au cluster :", "#   bash platform/install.sh"]
    return []


def clusters(ir: IR) -> dict[str, str]:
    files: dict[str, str] = {}
    cni = _cni(ir)
    app = ir.app
    if ir.has("k3s") and not ir.has("ansible"):
        flags = k3s_exec_flags(ir)
        body = [f'curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="{flags}" sh -',
                "# kubeconfig : /etc/rancher/k3s/k3s.yaml",
                "# Nœuds supplémentaires : K3S_URL=https://<serveur>:6443 K3S_TOKEN=<jeton> (voir /var/lib/rancher/k3s/server/node-token)"]
        if cni in ("cilium", "calico"):
            body.append(f"# Flannel est désactivé : les nœuds restent NotReady tant que {ir.catalog[cni].name} n'est pas installé.")
        if not _ingress(ir):
            body.append("# Traefik, fourni par k3s, sert de contrôleur d'entrée.")
        files["infra/cluster/install-k3s.sh"] = _script("Installe un serveur k3s sur ce nœud.", body + _platform_hint(ir))
        ir.cover("k3s")
    if ir.has("rke2"):
        rke_cni = {"cilium": "cilium", "calico": "calico", "flannel": "canal"}.get(cni or "", "canal")
        body = ["mkdir -p /etc/rancher/rke2",
                "cat > /etc/rancher/rke2/config.yaml <<'EOF'",
                f"cni: {rke_cni}",
                "EOF",
                "curl -sfL https://get.rke2.io | sh -",
                "systemctl enable --now rke2-server.service",
                "# kubeconfig : /etc/rancher/rke2/rke2.yaml"]
        if _ingress(ir):
            body.append("# RKE2 installe un contrôleur d'entrée par défaut : le désactiver avec la clé « disable » de "
                        "config.yaml (nom du chart selon votre version, voir la documentation RKE2).")
        files["infra/cluster/install-rke2.sh"] = _script("Installe un serveur RKE2 sur ce nœud.", body + _platform_hint(ir))
        ir.cover("rke2")
    if ir.has("kubeadm"):
        cidr = {"flannel": "10.244.0.0/16", "calico": "192.168.0.0/16"}.get(cni or "")
        init = "kubeadm init" + (f" --pod-network-cidr={cidr}" if cidr else "")
        body = ["# Prérequis sur chaque nœud : containerd, kubeadm, kubelet et kubectl installés, swap désactivé.",
                init,
                'mkdir -p "$HOME/.kube"',
                'cp /etc/kubernetes/admin.conf "$HOME/.kube/config"',
                "# Nœuds supplémentaires : kubeadm token create --print-join-command"]
        if cni:
            body.append(f"# Les nœuds restent NotReady tant que {ir.catalog[cni].name} n'est pas installé.")
        files["infra/cluster/install-kubeadm.sh"] = _script("Initialise le plan de contrôle avec kubeadm.",
                                                            body + _platform_hint(ir))
        ir.cover("kubeadm")
    if ir.has("microk8s"):
        body = ["snap install microk8s --classic",
                "microk8s status --wait-ready",
                "microk8s enable dns",
                "microk8s config > kubeconfig  # à copier sur le poste d'administration"]
        if cni and cni != "calico":
            body.append(f"# MicroK8s utilise Calico ; vérifier la prise en charge de {ir.catalog[cni].name} avant de l'installer.")
        files["infra/cluster/install-microk8s.sh"] = _script("Installe MicroK8s sur ce nœud.", body + _platform_hint(ir))
        ir.cover("microk8s")
    if ir.has("kind"):
        cfg: dict = {"kind": "Cluster", "apiVersion": "kind.x-k8s.io/v1alpha4",
                     "nodes": [{"role": "control-plane"}, {"role": "worker"}]}
        if cni:
            cfg["networking"] = {"disableDefaultCNI": True}
        files["infra/cluster/kind.yaml"] = dump_yaml(cfg)
        files["infra/cluster/create-kind.sh"] = _script(
            "Crée un cluster kind de développement.",
            [f"kind create cluster --name {app} --config infra/cluster/kind.yaml"] + _platform_hint(ir))
        ir.cover("kind")
    if ir.has("minikube"):
        opt = f" --cni={cni}" if cni else ""
        files["infra/cluster/create-minikube.sh"] = _script(
            "Démarre un cluster minikube de développement.", [f"minikube start --profile {app}{opt}"] + _platform_hint(ir))
        ir.cover("minikube")
    return files
