"""Lot 0.10 : Ansible — hôtes paramétrés, configuration, collections épinglées, connexion au registre."""

from __future__ import annotations

import shutil
import subprocess

import pytest
import yaml

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.model import Project, env_preset
from devops_builder.rules import RuleEngine

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
BASE = ("gitlab", "gitlab-ci", "buildkit", "harbor", "ansible")


def project(*tools: str, envs: str = "prod", **params) -> Project:
    p = Project(name="Site", target="vm", environments=env_preset(envs))
    p.app.image_name = "site"
    for t in tools:
        p.add(t, CATALOG[t].stage, **params.get(t.replace("-", "_"), {}))
    return p


def files_of(p: Project) -> dict[str, str]:
    return generate(p, CATALOG, ENGINE, allow_blocking=True).files


HARBOR = {"harbor": {"url": "registry.exemple.fr"}}


def test_hotes_et_compte_par_environnement():
    p = project(*BASE, "docker-compose", envs="staging-prod",
                ansible={"hosts": "app1.exemple.fr, app2.exemple.fr", "user": "ops"}, **HARBOR)
    p.env("staging").overrides["ansible"] = {"hosts": "recette.exemple.fr"}
    f = files_of(p)
    prod, staging = f["ansible/inventories/production.ini"], f["ansible/inventories/staging.ini"]
    assert "[app]\napp1.exemple.fr\napp2.exemple.fr\n" in prod and "ansible_user=ops" in prod
    assert "[app]\nrecette.exemple.fr\n" in staging and "deploy_env=staging" in staging
    assert "R34" not in {d.rule_id for d in ENGINE.evaluate(p) if "Ansible" in d.message}


def test_hotes_d_exemple_signales():
    diags = ENGINE.evaluate(project(*BASE, "docker-compose", **HARBOR))
    assert any(d.rule_id == "R34" and "Hôtes de l'application" in d.message for d in diags)


def test_ci_installe_ansible_et_les_collections_epinglees():
    f = files_of(project(*BASE, "docker-compose", **HARBOR))
    job = yaml.safe_load(f[".gitlab-ci.yml"])["deploy"]
    assert job["image"]["name"] == "python:3.12-alpine"
    assert job["variables"]["ANSIBLE_CONFIG"] == "ansible/ansible.cfg"
    assert "ansible-galaxy collection install -r ansible/requirements.yml" in job["script"]
    assert any("SSH_KNOWN_HOSTS" in line for line in job["script"])
    req = yaml.safe_load(f["ansible/requirements.yml"])
    assert req["collections"][0]["name"] == "community.docker" and "<" in req["collections"][0]["version"]
    assert "StrictHostKeyChecking=accept-new" in f["ansible/ansible.cfg"]


def test_connexion_au_registre_avant_le_tirage():
    f = files_of(project(*BASE, "docker-compose", **HARBOR))
    tasks = yaml.safe_load(f["ansible/deploy.yml"])[0]["tasks"]
    names = [t["name"] for t in tasks]
    login = names.index("Se connecter au registre d'images")
    assert login < names.index("Démarrer les services")
    assert tasks[login]["no_log"] is True and "--password-stdin" in tasks[login]["ansible.builtin.command"]["argv"]
    script = " ".join(yaml.safe_load(f[".gitlab-ci.yml"])["deploy"]["script"])
    assert 'DEPLOY_REGISTRY="registry.exemple.fr" DEPLOY_REGISTRY_USER="$REGISTRY_USER"' in script
    gitlab = files_of(project("gitlab", "gitlab-ci", "buildkit", "ansible", "docker-compose"))
    assert 'DEPLOY_REGISTRY="$CI_REGISTRY"' in gitlab[".gitlab-ci.yml"]


def test_deploiement_ssh_se_connecte_aussi_au_registre():
    p = Project(target="docker-host")
    for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", "docker-compose"):
        p.add(t, CATALOG[t].stage)
    p.bricks_for("harbor")[0].params = {"url": "registry.exemple.fr"}
    script = " ".join(yaml.safe_load(files_of(p)[".gitlab-ci.yml"])["deploy"]["script"])
    assert 'echo "$REGISTRY_PASSWORD" | ssh "$DEPLOY_HOST" "docker login registry.exemple.fr' in script
    assert script.index("docker login") < script.index("docker compose -p")


def test_registre_cloud_laisse_a_l_identite_de_la_machine():
    p = Project(target="docker-host")
    for t in ("github", "github-actions", "buildkit", "aws", "ecr", "docker-compose"):
        p.add(t, CATALOG[t].stage)
    f = files_of(p)
    assert "docker login" not in f[".github/workflows/pipeline.yml"].split("deploy:")[-1]
    assert "docker-credential-ecr-login" in f["PIPELINE.md"]


def test_ansible_sans_compose_lance_l_application_seule():
    f = files_of(project(*BASE, **HARBOR))
    tasks = yaml.safe_load(f["ansible/deploy.yml"])[0]["tasks"]
    start = tasks[-1]["community.docker.docker_compose_v2"]
    assert start["definition"]["services"]["site"]["ports"] == ["8000:8000"]
    assert start["wait"] is True
    assert not any("docker-compose.yml" in str(t) for t in tasks)


def test_preparation_des_hotes_depuis_le_depot_docker():
    site = yaml.safe_load(files_of(project(*BASE, "docker-compose", **HARBOR))["ansible/site.yml"])
    blocks = {t["name"]: t for t in site[0]["tasks"]}
    debian = blocks["Docker sur Debian et Ubuntu"]
    assert debian["when"] == "ansible_os_family == 'Debian'"
    assert any("ansible.builtin.deb822_repository" in t for t in debian["block"])
    assert "docker-compose-plugin" in str(blocks["Docker sur RHEL, Rocky, Alma et Fedora"])


@pytest.mark.skipif(not shutil.which("ansible-playbook"), reason="ansible-core absent")
def test_playbooks_valides(tmp_path):
    p = project(*BASE, "docker-compose", "postgresql", "k3s", envs="staging-prod", **HARBOR)
    result = generate(p, CATALOG, ENGINE, allow_blocking=True)
    result.write(tmp_path)
    (tmp_path / ".secrets").mkdir()
    env = {"ANSIBLE_CONFIG": "ansible/ansible.cfg", "PATH": __import__("os").environ["PATH"]}
    r = subprocess.run(["ansible-playbook", "--syntax-check", "-i", "ansible/inventories/staging.ini",
                        "ansible/deploy.yml", "ansible/site.yml"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    if shutil.which("ansible-lint"):
        r = subprocess.run(["ansible-lint", "--offline", "-q", "ansible/"], cwd=tmp_path, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
