# SPDX-License-Identifier: Apache-2.0
"""Hôte Docker essayé à la main : compte root sans sudo, section « Essai à la main, sans CI » du guide."""

from __future__ import annotations

from test_data import files_of, project

BASE = ("gitlab", "gitlab-ci", "buildkit", "docker-compose", "zabbix")


def guide(user: str | None, *tools: str) -> tuple[str, dict[str, str]]:
    p = project("docker-host", *BASE, *tools, envs="prod", **({"ansible": {"hosts": "192.168.1.28", "user": user}}
                                                               if user else {}))
    files = files_of(p)
    return files["docs/mise-en-route.md"], files


def test_compte_root_sans_creation_ni_sudo():
    text, files = guide("root", "ansible")
    assert "useradd" not in text and "sudoers" not in text and "/home/root" not in text
    assert "ssh-copy-id -i ci_deploy.pub root@<hôte>" in text
    assert "ansible_become=false" in files["ansible/inventory.ini"]


def test_compte_ordinaire_inchange():
    text, files = guide("deploy", "ansible")
    assert "sudo useradd -m -s /bin/bash deploy" in text and "NOPASSWD" in text
    assert "ansible_become" not in files["ansible/inventory.ini"]


def test_essai_a_la_main():
    text, files = guide(None)
    assert "## " in text and "Essai à la main, sans CI" in text
    assert 'ZABBIX_DB_PASSWORD="$(openssl rand -hex 24)" sh deploy/secrets.sh deploy/secrets' in text
    assert "docker compose config --services" in text
    assert "releases/latest/download/docker-compose-linux-x86_64" in text


def test_pas_d_essai_a_la_main_sur_kubernetes():
    p = project("kubernetes", "github", "github-actions", "buildkit", "ghcr", "k3s", "helm")
    assert "Essai à la main" not in files_of(p).get("docs/mise-en-route.md", "")
