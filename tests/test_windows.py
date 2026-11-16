# SPDX-License-Identifier: Apache-2.0
"""Hôtes Windows Server : Ansible (WinRM ou SSH), Docker et Compose sur conteneurs Windows."""

from __future__ import annotations

import yaml
from test_data import CATALOG, ENGINE, files_of, project

from devops_builder.generators import generate

BASE = ("gitlab", "gitlab-ci", "buildkit", "docker-compose", "ansible", "windows-server")


def win(**params):
    return project("vm", *BASE, envs="prod", **({"windows_server": params} if params else {}))


def test_inventaire_winrm_par_defaut():
    inv = files_of(win())["ansible/inventory.ini"]
    assert "ansible_connection=winrm" in inv and "ansible_port=5986" in inv and "ansible_user=Administrator" in inv
    assert "lookup('ansible.builtin.env', 'ANSIBLE_PASSWORD')" in inv and "ansible_become" not in inv


def test_inventaire_ssh():
    inv = files_of(win(connection="ssh", user="CORP\\deploy"))["ansible/inventory.ini"]
    assert "ansible_connection=ssh" in inv and "ansible_shell_type=powershell" in inv and "ansible_user=CORP\\deploy" in inv
    assert "winrm" not in inv


def test_playbooks_windows():
    files = files_of(win())
    deploy = yaml.safe_load(files["ansible/deploy.yml"])[0]
    assert "become" not in deploy and deploy["vars"]["app_dir"] == "C:\\apps\\{{ project }}"
    names = [next(k for k in t if k.startswith("ansible.windows")) for t in deploy["tasks"]]
    assert names[0] == "ansible.windows.win_file" and names[-1] == "ansible.windows.win_shell"
    start = deploy["tasks"][-1]
    assert "docker compose" in start["ansible.windows.win_shell"] and start["environment"]["IMAGE"] == "{{ image }}"
    site = yaml.safe_load(files["ansible/site.yml"])[0]
    assert any("win_feature" in str(t) for t in site["tasks"]) and any("install-docker-ce.ps1" in str(t) for t in site["tasks"])
    assert "ansible.windows" in files["ansible/requirements.yml"] and "community.docker" not in files["ansible/requirements.yml"]


def test_ci_winrm_et_ssh():
    script = "\n".join(yaml.safe_load(files_of(win())[".gitlab-ci.yml"])["deploy"]["script"])
    assert "pip install --no-cache-dir pywinrm" in script and "id_ed25519" not in script
    ssh = "\n".join(yaml.safe_load(files_of(win(connection="ssh"))[".gitlab-ci.yml"])["deploy"]["script"])
    assert "id_ed25519" in ssh and "pywinrm" not in ssh
    r = generate(win(), CATALOG, ENGINE, allow_blocking=True)
    assert "ANSIBLE_PASSWORD" in {v.name for v in r.ir.variables} and "SSH_PRIVATE_KEY" not in {v.name for v in r.ir.variables}
    assert "windows-server" in r.ir.covered
    assert any("image Windows" in n for n in r.ir.notes)


def test_r63():
    def messages(p):
        return " ".join(d.message for d in ENGINE.evaluate(p) if d.rule_id == "R63")
    assert messages(win()) == ""
    assert "Ansible et Docker Compose" in messages(project("vm", "gitlab", "gitlab-ci", "buildkit", "windows-server", envs="prod"))
    assert "Traefik" in messages(project("vm", *BASE, "traefik", envs="prod"))


def test_sans_windows_inchange():
    inv = files_of(project("vm", *BASE[:-1], envs="prod"))["ansible/inventory.ini"]
    assert "winrm" not in inv and "ansible_become" not in inv.replace("ansible_become=false", "")
