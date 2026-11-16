# SPDX-License-Identifier: Apache-2.0
"""Accès privé (Tailscale, WireGuard, bastion SSH) et machines Proxmox VE."""

from __future__ import annotations

import yaml
from test_data import CATALOG, ENGINE, files_of, project

from devops_builder.generators import generate
from devops_builder.model import Project

BASE = ("gitlab", "gitlab-ci", "buildkit", "docker-compose")


def rules(p: Project) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in ENGINE.evaluate(p):
        out[d.rule_id] = f"{out[d.rule_id]} {d.message}" if d.rule_id in out else d.message
    return out


def deploy_script(files: dict[str, str]) -> str:
    return "\n".join(yaml.safe_load(files[".gitlab-ci.yml"])["deploy"]["script"])


def test_tailscale_dans_le_deploiement_ssh():
    files = files_of(project("docker-host", *BASE, "tailscale", envs="prod"))
    script = deploy_script(files)
    assert "tailscaled --tun=userspace-networking" in script and 'tailscale up --authkey="$TAILSCALE_AUTHKEY"' in script
    assert "ProxyCommand nc -X 5 -x localhost:1055" in script
    assert script.index("id_ed25519") < script.index("tailscaled") < script.index("mkdir -p /opt/")
    assert "TAILSCALE_AUTHKEY" in files["scripts/ci-variables.md"] if "scripts/ci-variables.md" in files else True
    assert "ansible/tailscale.yml" not in files   # sans Ansible : pas de playbook


def test_tailscale_et_ansible():
    files = files_of(project("vm", *BASE, "ansible", "tailscale", envs="prod"))
    play = yaml.safe_load(files["ansible/tailscale.yml"])[0]
    assert play["hosts"] == "app" and any("'up'" in str(t) for t in play["tasks"])
    assert 'tailscale up --authkey="$TAILSCALE_AUTHKEY"' in deploy_script(files)


def test_wireguard():
    files = files_of(project("vm", *BASE, "ansible", "wireguard", envs="prod"))
    script = deploy_script(files)
    assert "wg-quick up wg0" in script and 'printf \'%s\\n\' "$WG_CONFIG"' in script
    play = yaml.safe_load(files["ansible/wireguard.yml"])[0]
    assert play["vars"]["wg_peers"] == [] and "wg genkey" in str(play["tasks"])
    assert "PrivateKey" in str(play["tasks"]) and "BEGIN" not in files["ansible/wireguard.yml"]   # clé générée sur l'hôte


def test_bastion():
    script = deploy_script(files_of(project("docker-host", *BASE, "ssh-bastion", envs="prod")))
    assert 'BASTION="${BASTION_HOST#*@}"' in script and "ProxyJump %s" in script
    assert script.index("ProxyJump") > script.index("id_ed25519")


def test_variables_ci_declarees():
    r = generate(project("docker-host", *BASE, "ssh-bastion", "tailscale", "wireguard", envs="prod"), CATALOG, ENGINE,
                 allow_blocking=True)
    names = {v.name for v in r.ir.variables}
    assert {"BASTION_HOST", "TAILSCALE_AUTHKEY", "WG_CONFIG"} <= names
    assert {"tailscale", "wireguard", "ssh-bastion"} <= r.ir.covered


def test_r62():
    assert "R62" not in rules(project("docker-host", *BASE, "tailscale", envs="prod"))
    assert "n'es" not in rules(project("docker-host", *BASE, "tailscale", envs="prod")).get("R62", "")
    kube = project("kubernetes", "github", "github-actions", "buildkit", "ghcr", "k3s", "helm", "ssh-bastion", envs="prod")
    assert "ne passe pas par SSH" in rules(kube)["R62"]
    both = rules(project("docker-host", *BASE, "tailscale", "ssh-bastion", envs="prod"))["R62"]
    assert "deux chemins d'accès" in both


def test_proxmox_machines_et_variables():
    p = project("vm", *BASE, "ansible", "opentofu", "proxmox", "proxmox-vm", envs="staging-prod",
                proxmox={"endpoint": "https://pve.lab:8006/", "node": "pve2", "template_id": 9100, "datastore": "ssd",
                         "bridge": "vmbr1"})
    r = generate(p, CATALOG, ENGINE, allow_blocking=True)
    main = r.files["infra/terraform/main.tf"]
    assert 'resource "proxmox_virtual_environment_vm" "staging"' in main and 'resource "proxmox_virtual_environment_vm" "production"' in main
    assert 'node_name = "pve2"' in main and "vm_id = 9100" in main and 'datastore_id = "ssd"' in main
    assert 'bridge = "vmbr1"' in main and 'address = "dhcp"' in main
    assert 'provider "proxmox"' in main and 'endpoint = "https://pve.lab:8006/"' in main
    assert "bpg/proxmox" in r.files["infra/terraform/versions.tf"]
    assert 'vm.ipv4_addresses[1][0]' in r.files["infra/terraform/outputs.tf"]
    assert {"PROXMOX_VE_API_TOKEN", "TF_VAR_ssh_public_key"} <= {v.name for v in r.ir.variables}
    assert {"proxmox", "proxmox-vm"} <= r.ir.covered
    assert not [d for d in r.diagnostics if d.severity.name == "BLOCKING"]


def test_proxmox_catalogue():
    assert CATALOG["proxmox"].services["compute"] == "proxmox-vm" and CATALOG["proxmox-vm"].provider == "proxmox"
    assert CATALOG["proxmox"].auth == ["static"]
