# SPDX-License-Identifier: Apache-2.0
"""Ansible : inventaires par environnement, préparation des hôtes, déploiement Compose.

La CI lance `ansible-playbook` depuis la racine du dépôt avec ANSIBLE_CONFIG=ansible/ansible.cfg.
Les collections sont épinglées dans ansible/requirements.yml ; les hôtes n'ont besoin que de
Docker et de son extension Compose (installés par site.yml depuis le dépôt officiel de Docker).
"""

from __future__ import annotations

import re

from ..ir import IR, ansible_hosts, host_registry
from .common import HEADER, dump_yaml

ANSIBLE_CORE = "ansible-core>=2.21,<2.22"
COMMUNITY_DOCKER = ">=4.0.0,<6.0.0"
CONFIG = "ansible/ansible.cfg"
DOCKER_PACKAGES = ["docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"]

_CFG = f"""# {HEADER}
# Lu par la CI via ANSIBLE_CONFIG=ansible/ansible.cfg (Ansible ignore un ansible.cfg placé dans
# un dossier accessible en écriture à tous, ce qui arrive sur les runners).
[defaults]
interpreter_python = auto_silent
retry_files_enabled = False
forks = 10
stdout_callback = default
result_format = yaml

[ssh_connection]
pipelining = True
# Clé d'hôte : SSH_KNOWN_HOSTS (variable CI) l'impose ; sinon la première connexion l'enregistre.
ssh_args = -o ControlMaster=auto -o ControlPersist=60s -o StrictHostKeyChecking=accept-new
"""


def _inventory(ir: IR, env) -> str:
    p = ir.params("ansible", env)
    user = p.get("user") or "deploy"
    lines = [f"# {HEADER}"]
    if ir.multi_env:
        lines.append(f"# Environnement : {env.display} — hôtes : paramètre « Hôtes de l'application » de la brique Ansible")
    from .hosts import INVENTORY_SCRIPT, creates_hosts
    if creates_hosts(ir):
        lines += [f"# Machines créées par Terraform : {INVENTORY_SCRIPT} {env.id} remplit ce groupe.", "[app]", ""]
    else:
        lines += ["[app]", *ansible_hosts(ir, env), ""]
    if ir.has("k3s"):
        lines += ["[k3s]", f"k3s1{('.' + env.id) if ir.multi_env else ''}.example.com", ""]
    lines += ["[all:vars]", f"ansible_user={user}", f"deploy_env={env.id}", ""]
    return "\n".join(lines)


def _app_definition(ir: IR) -> dict:
    """Projet Compose minimal quand le pipeline n'a pas de brique Docker Compose : l'application seule."""
    port = ir.project.app.port
    return {"services": {ir.app: {"image": "{{ image }}", "restart": "unless-stopped",
                                  "environment": {"PORT": str(port)}, "ports": [f"{port}:{port}"]}}}


def ansible(ir: IR) -> dict[str, str]:
    from .deploy import _ansible_db_tasks, _ports_shifted
    files: dict[str, str] = {}
    for env in ir.envs:
        files[ir.inventory(env)] = _inventory(ir, env)
    compose = ir.has("docker-compose")
    tasks: list[dict] = [
        {"name": "Créer le répertoire de l'application",
         "ansible.builtin.file": {"path": "{{ app_dir }}", "state": "directory", "mode": "0755"}},
    ]
    if compose:
        tasks.append({"name": "Copier le fichier Compose",
                      "ansible.builtin.copy": {"src": "../deploy/docker-compose.yml",
                                               "dest": "{{ app_dir }}/docker-compose.yml", "mode": "0644"}})
        if _ports_shifted(ir):
            tasks.append({"name": "Copier les ports de l'environnement",
                          "ansible.builtin.copy": {"src": "../deploy/env/{{ deploy_env }}.env",
                                                   "dest": "{{ app_dir }}/.env", "mode": "0644"}})
        tasks += _ansible_db_tasks(ir)
    from . import registre
    tasks += registre.ansible_tasks(ir)
    if host_registry(ir) is not None:
        tasks.append({
            "name": "Se connecter au registre d'images",
            "ansible.builtin.command": {
                "argv": ["docker", "login", "{{ registry_host }}", "--username", "{{ registry_user }}",
                         "--password-stdin"],
                "stdin": "{{ registry_password }}"},
            "no_log": True,
            "changed_when": False,
            "when": "registry_password | length > 0"})
    start: dict = {"project_name": "{{ project }}", "pull": "always", "state": "present",
                   "wait": True, "wait_timeout": 180}
    if compose:
        start = {"project_src": "{{ app_dir }}", **start}
    else:
        start = {"project_src": "{{ app_dir }}", "definition": _app_definition(ir), **start}
    tasks.append({"name": "Démarrer les services",
                  "community.docker.docker_compose_v2": start,
                  "environment": {"IMAGE": "{{ image }}", **({"APP_HOST": "{{ app_host }}"} if ir.has("traefik") else {})}})
    variables = {"image": f"{ir.image_ref}:latest", "project": ir.app, "app_dir": "/opt/{{ project }}"}
    if ir.has("traefik"):
        from ..ports import app_hostname
        variables["app_host"] = app_hostname(ir.project)
    if host_registry(ir) is not None:
        variables.update({
            "registry_host": "{{ lookup('ansible.builtin.env', 'DEPLOY_REGISTRY') }}",
            "registry_user": "{{ lookup('ansible.builtin.env', 'DEPLOY_REGISTRY_USER') }}",
            "registry_password": "{{ lookup('ansible.builtin.env', 'DEPLOY_REGISTRY_PASSWORD') }}"})
    files["ansible/deploy.yml"] = dump_yaml(indent_lists=True, data=[{
        "name": f"Déployer {ir.app}",
        "hosts": "app",
        "become": True,
        "serial": 1,  # un hôte après l'autre : l'application reste servie pendant la mise à jour
        "vars": variables,
        "tasks": tasks,
    }])
    files["ansible/site.yml"] = dump_yaml(_site(ir), indent_lists=True)
    files[CONFIG] = _CFG
    files["ansible/requirements.yml"] = dump_yaml(
        {"collections": [{"name": "community.docker", "version": COMMUNITY_DOCKER}]}, indent_lists=True)
    ir.notes.append("Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook "
                    f"-i {ir.inventory(ir.envs[0])} ansible/site.yml` (Docker depuis son dépôt officiel, Debian, "
                    "Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.")
    if not compose:
        ir.notes.append("Ansible sans brique Docker Compose : l'application est lancée seule, d'après une définition "
                        "Compose écrite dans ansible/deploy.yml.")
    ir.cover("ansible")
    return files


def _site(ir: IR) -> list[dict]:
    debian_repo = "https://download.docker.com/linux/{{ ansible_distribution | lower }}"
    site: list[dict] = [{
        "name": "Préparer les hôtes Docker",
        "hosts": "app",
        "become": True,
        "tasks": [
            {"name": "Docker déjà installé ?",
             "ansible.builtin.stat": {"path": "/usr/bin/docker"},
             "register": "docker_bin"},
            {"name": "Prérequis (Debian, Ubuntu)",
             "when": "ansible_os_family == 'Debian'",
             "ansible.builtin.apt": {"name": ["ca-certificates", "curl", "python3-yaml"], "update_cache": True,
                                     "cache_valid_time": 3600}},
            {"name": "Docker sur Debian et Ubuntu",
             "when": "ansible_os_family == 'Debian' and not docker_bin.stat.exists",
             "block": [
                 {"name": "Clé du dépôt Docker",
                  "ansible.builtin.get_url": {"url": f"{debian_repo}/gpg", "dest": "/etc/apt/keyrings/docker.asc",
                                              "mode": "0644"}},
                 {"name": "Dépôt Docker",
                  "ansible.builtin.deb822_repository": {
                      "name": "docker", "types": ["deb"], "uris": [debian_repo],
                      "suites": ["{{ ansible_distribution_release }}"], "components": ["stable"],
                      "signed_by": "/etc/apt/keyrings/docker.asc"}},
                 {"name": "Paquets Docker",
                  "ansible.builtin.apt": {"name": DOCKER_PACKAGES, "update_cache": True}},
             ]},
            {"name": "Docker sur RHEL, Rocky, Alma et Fedora",
             "when": "ansible_os_family == 'RedHat' and not docker_bin.stat.exists",
             "block": [
                 {"name": "Dépôt Docker",
                  "ansible.builtin.get_url": {
                      "url": "https://download.docker.com/linux/"
                             "{{ 'fedora' if ansible_distribution == 'Fedora' else 'rhel' }}/docker-ce.repo",
                      "dest": "/etc/yum.repos.d/docker-ce.repo", "mode": "0644"}},
                 {"name": "Paquets Docker",
                  "ansible.builtin.dnf": {"name": [*DOCKER_PACKAGES, "python3-pyyaml"], "state": "present"}},
             ]},
            {"name": "Activer Docker",
             "ansible.builtin.service": {"name": "docker", "state": "started", "enabled": True}},
        ],
    }]
    if ir.has("k3s"):
        from .extras import k3s_exec_flags
        site.append({
            "name": "Installer k3s",
            "hosts": "k3s",
            "become": True,
            "tasks": [{"name": "Installer k3s (script officiel)",
                       "ansible.builtin.shell": "set -o pipefail && curl -sfL https://get.k3s.io | sh -",
                       "args": {"creates": "/usr/local/bin/k3s", "executable": "/bin/bash"},
                       "environment": {"INSTALL_K3S_EXEC": k3s_exec_flags(ir)}}],
        })
        ir.cover("k3s")
    return site


def lint_hosts(value: str) -> list[str]:
    return [h for h in re.split(r"[\s,]+", value or "") if h]
