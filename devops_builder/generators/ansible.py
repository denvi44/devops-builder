# SPDX-License-Identifier: Apache-2.0
"""Ansible : inventaires par environnement, préparation des hôtes, déploiement Compose.

La CI lance `ansible-playbook` depuis la racine du dépôt avec ANSIBLE_CONFIG=ansible/ansible.cfg.
Les collections sont épinglées dans ansible/requirements.yml ; les hôtes n'ont besoin que de
Docker et de son extension Compose (installés par site.yml depuis le dépôt officiel de Docker).
"""

from __future__ import annotations

import re

from ..ir import IR, ansible_hosts, host_registry, project_components
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
    if ir.has("windows-server"):
        w = ir.params("windows-server", env)
        user = w.get("user") or "Administrator"
        lines += ["[all:vars]", f"ansible_user={user}", f"deploy_env={env.id}"]
        if (w.get("connection") or "winrm") == "ssh":
            lines += ["ansible_connection=ssh", "ansible_shell_type=powershell"]
        else:
            lines += ["ansible_connection=winrm", "ansible_port=5986", "ansible_winrm_transport=ntlm",
                      "# Certificat auto-signé (laboratoire) : remplacer validate par ignore, à éviter en production.",
                      "ansible_winrm_server_cert_validation=validate",
                      "ansible_password={{ lookup('ansible.builtin.env', 'ANSIBLE_PASSWORD') }}"]
        lines.append("")
        return "\n".join(lines)
    lines += ["[all:vars]", f"ansible_user={user}", f"deploy_env={env.id}"]
    if user == "root":
        lines.append("ansible_become=false   # déjà root : pas de sudo (absent de certains NAS)")
    lines.append("")
    return "\n".join(lines)


def _app_definition(ir: IR) -> dict:
    """Projet Compose minimal quand le pipeline n'a pas de brique Docker Compose : l'application seule."""
    port = ir.project.app.port
    from .deploy import component_url_env
    app_env = {"PORT": str(port), **component_url_env(ir, lambda c: c.id)}
    services = {ir.app: {"image": "{{ image }}", "restart": "unless-stopped",
                         "environment": app_env, "ports": [f"{port}:{port}"]}}
    for c in project_components(ir):
        svc: dict = {"image": "{{ " + c.env_name.lower() + " }}", "restart": "unless-stopped",
                     "environment": {"PORT": str(c.port)}}
        if c.public:
            svc["ports"] = [f"{c.port}:{c.port}"]
        services[c.id] = svc
    return {"services": services}


def ansible(ir: IR) -> dict[str, str]:
    from .deploy import _ansible_db_tasks, _ports_shifted
    files: dict[str, str] = {}
    for env in ir.envs:
        files[ir.inventory(env)] = _inventory(ir, env)
    if ir.has("windows-server"):
        return _windows(ir, files)
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
                  "environment": {"IMAGE": "{{ image }}",
                                  **{c.env_name: "{{ " + c.env_name.lower() + " }}" for c in project_components(ir)},
                                  **({"APP_HOST": "{{ app_host }}"} if ir.has("traefik") else {})}})
    variables = {"image": f"{ir.image_ref}:latest", "project": ir.app, "app_dir": "/opt/{{ project }}"}
    for c in project_components(ir):
        variables[c.env_name.lower()] = f"{ir.image_ref}:{c.id}-latest"
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


_DOCKER_SCRIPT = ("https://raw.githubusercontent.com/microsoft/Windows-Containers/Main/helpful_tools/"
                  "Install-DockerCE/install-docker-ce.ps1")
_COMPOSE_EXE = "https://github.com/docker/compose/releases/latest/download/docker-compose-windows-x86_64.exe"


def _windows(ir: IR, files: dict[str, str]) -> dict[str, str]:
    """Hôtes Windows Server : Conteneurs + Docker Engine + Compose, application déployée comme conteneur Windows."""
    from .deploy import _ports_shifted
    w = ir.params("windows-server")
    app_dir = (w.get("app_dir") or "C:\\apps").rstrip("\\")
    tasks: list[dict] = [
        {"name": "Créer le dossier de l'application",
         "ansible.windows.win_file": {"path": "{{ app_dir }}", "state": "directory"}},
        {"name": "Copier le fichier Compose",
         "ansible.windows.win_copy": {"src": "../deploy/docker-compose.yml",
                                      "dest": "{{ app_dir }}\\docker-compose.yml"}},
    ]
    if _ports_shifted(ir):
        tasks.append({"name": "Copier les ports de l'environnement",
                      "ansible.windows.win_copy": {"src": "../deploy/env/{{ deploy_env }}.env",
                                                   "dest": "{{ app_dir }}\\.env"}})
    if host_registry(ir) is not None:
        tasks.append({
            "name": "Se connecter au registre d'images",
            "ansible.windows.win_shell": "$env:DEPLOY_REGISTRY_PASSWORD | docker login $env:DEPLOY_REGISTRY "
                                         "--username $env:DEPLOY_REGISTRY_USER --password-stdin",
            "environment": {"DEPLOY_REGISTRY": "{{ lookup('ansible.builtin.env', 'DEPLOY_REGISTRY') }}",
                            "DEPLOY_REGISTRY_USER": "{{ lookup('ansible.builtin.env', 'DEPLOY_REGISTRY_USER') }}",
                            "DEPLOY_REGISTRY_PASSWORD": "{{ lookup('ansible.builtin.env', 'DEPLOY_REGISTRY_PASSWORD') }}"},
            "no_log": True, "changed_when": False})
    tasks.append({
        "name": "Démarrer les services",
        "ansible.windows.win_shell": "docker compose --project-name {{ project }} up --detach --pull always --wait",
        "args": {"chdir": "{{ app_dir }}"},
        "environment": {"IMAGE": "{{ image }}",
                        **{c.env_name: "{{ " + c.env_name.lower() + " }}" for c in project_components(ir)}},
    })
    variables = {"image": f"{ir.image_ref}:latest", "project": ir.app, "app_dir": app_dir + "\\{{ project }}"}
    for c in project_components(ir):
        variables[c.env_name.lower()] = f"{ir.image_ref}:{c.id}-latest"
    files["ansible/deploy.yml"] = dump_yaml(indent_lists=True, data=[{
        "name": f"Déployer {ir.app} sur Windows Server",
        "hosts": "app",
        "serial": 1,
        "vars": variables,
        "tasks": tasks,
    }])
    files["ansible/site.yml"] = dump_yaml([{
        "name": "Préparer les hôtes Windows Server (conteneurs, Docker, Compose)",
        "hosts": "app",
        "tasks": [
            {"name": "Fonctionnalité Conteneurs",
             "ansible.windows.win_feature": {"name": "Containers", "state": "present"}, "register": "containers"},
            {"name": "Redémarrer si la fonctionnalité l'exige",
             "ansible.windows.win_reboot": {}, "when": "containers.reboot_required"},
            {"name": "Docker déjà installé ?",
             "ansible.windows.win_stat": {"path": "C:\\Program Files\\Docker\\docker.exe"}, "register": "docker_exe"},
            {"name": "Script d'installation de Docker (Microsoft)",
             "ansible.windows.win_get_url": {"url": _DOCKER_SCRIPT, "dest": "C:\\Windows\\Temp\\install-docker-ce.ps1"},
             "when": "not docker_exe.stat.exists"},
            {"name": "Installer Docker Engine",
             "ansible.windows.win_shell": "C:\\Windows\\Temp\\install-docker-ce.ps1",
             "when": "not docker_exe.stat.exists"},
            {"name": "Dossier des extensions Docker",
             "ansible.windows.win_file": {"path": "C:\\Program Files\\Docker\\cli-plugins", "state": "directory"}},
            {"name": "Docker Compose (extension)",
             "ansible.windows.win_get_url": {"url": _COMPOSE_EXE,
                                             "dest": "C:\\Program Files\\Docker\\cli-plugins\\docker-compose.exe"}},
            {"name": "Service Docker démarré",
             "ansible.windows.win_service": {"name": "docker", "state": "started", "start_mode": "auto"}},
        ],
    }], indent_lists=True)
    files[CONFIG] = _CFG
    files["ansible/requirements.yml"] = dump_yaml(
        {"collections": [{"name": "ansible.windows", "version": ">=3.0.0,<4.0.0"}]}, indent_lists=True)
    ir.notes.append("Windows Server : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg "
                    f"ansible-playbook -i {ir.inventory(ir.envs[0])} ansible/site.yml`. WinRM : écouteur HTTPS (5986) "
                    "à activer sur l'hôte (script ConfigureRemotingForAnsible.ps1) ; le mot de passe du compte se donne "
                    "dans ANSIBLE_PASSWORD. L'image de l'application doit être une image Windows, construite sur un "
                    "runner Windows : un build Linux ne convient pas.")
    ir.cover("ansible", "windows-server")
    return files


def _site(ir: IR) -> list[dict]:
    debian_repo = "https://download.docker.com/linux/{{ ansible_facts['distribution'] | lower }}"
    site: list[dict] = [{
        "name": "Préparer les hôtes Docker",
        "hosts": "app",
        "become": True,
        "tasks": [
            {"name": "Docker déjà installé ?",
             "ansible.builtin.stat": {"path": "/usr/bin/docker"},
             "register": "docker_bin"},
            {"name": "Prérequis (Debian, Ubuntu)",
             "when": "ansible_facts['os_family'] == 'Debian'",
             "ansible.builtin.apt": {"name": ["ca-certificates", "curl", "python3-yaml"], "update_cache": True,
                                     "cache_valid_time": 3600}},
            {"name": "Docker sur Debian et Ubuntu",
             "when": "ansible_facts['os_family'] == 'Debian' and not docker_bin.stat.exists",
             "block": [
                 {"name": "Clé du dépôt Docker",
                  "ansible.builtin.get_url": {"url": f"{debian_repo}/gpg", "dest": "/etc/apt/keyrings/docker.asc",
                                              "mode": "0644"}},
                 {"name": "Dépôt Docker",
                  "ansible.builtin.deb822_repository": {
                      "name": "docker", "types": ["deb"], "uris": [debian_repo],
                      "suites": ["{{ ansible_facts['distribution_release'] }}"], "components": ["stable"],
                      "signed_by": "/etc/apt/keyrings/docker.asc"}},
                 {"name": "Paquets Docker",
                  "ansible.builtin.apt": {"name": DOCKER_PACKAGES, "update_cache": True}},
             ]},
            {"name": "Docker sur RHEL, Rocky, Alma et Fedora",
             "when": "ansible_facts['os_family'] == 'RedHat' and not docker_bin.stat.exists",
             "block": [
                 {"name": "Dépôt Docker",
                  "ansible.builtin.get_url": {
                      "url": "https://download.docker.com/linux/"
                             "{{ 'fedora' if ansible_facts['distribution'] == 'Fedora' else 'rhel' }}/docker-ce.repo",
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
