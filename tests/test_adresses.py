# SPDX-License-Identifier: Apache-2.0
"""0.21 : adresses IP (registres, entrée) et registre auto-hébergé en HTTP simple."""

from __future__ import annotations

import json

import pytest
import yaml

from devops_builder.addresses import host_part, is_ip, plain_http
from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.model import Project, env_preset
from devops_builder.rules import RuleEngine

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)


@pytest.mark.parametrize("value,ip", [("192.168.1.20", True), ("192.168.1.20:5000", True), ("10.0.0.1", True),
                                      ("registry.example.com", False), ("registry.local:5000", False),
                                      ("grafana.192.168.1.20.nip.io", False), ("localhost", False), ("::1", True)])
def test_is_ip(value, ip):
    assert is_ip(value) is ip


def test_host_part():
    assert host_part("https://192.168.1.20:5000/app") == "192.168.1.20"
    assert host_part("[::1]:5000") == "::1"


@pytest.mark.parametrize("value,plain", [("192.168.1.20:5000", True), ("localhost:5000", True),
                                         ("registry.example.com", False), ("registry.local:5000", False)])
def test_plain_http(value, plain):
    assert plain_http(value) is plain


def project(registry: str, url: str, target: str = "docker-host", *tools: str) -> Project:
    p = Project(name="t", target=target, environments=env_preset("staging-prod"))
    for t in ("gitlab", "gitlab-ci", "buildkit", registry, *tools):
        p.add(t, CATALOG[t].stage)
    p.bricks_for(registry)[0].params["url"] = url
    return p


def test_ansible_declare_le_registre_http():
    f = generate(project("distribution", "192.168.1.20:5000", "docker-host", "ansible", "docker-compose"), CATALOG).files
    play = yaml.safe_load(f["ansible/deploy.yml"])[0]
    names = [t["name"] for t in play["tasks"]]
    assert any("192.168.1.20:5000 en HTTP simple" in n for n in names)
    task = next(t for t in play["tasks"] if "insecure" in t["name"])
    assert task["ansible.builtin.command"]["argv"][-1] == "192.168.1.20:5000"
    assert names.index(task["name"]) < names.index("Se connecter au registre d'images")


def test_fusion_du_fichier_daemon(tmp_path, monkeypatch):
    """Le fragment fusionne la clé sans perdre le reste du fichier et reste idempotent."""
    from devops_builder.generators.registre import DAEMON_SNIPPET
    daemon = tmp_path / "daemon.json"
    daemon.write_text(json.dumps({"log-driver": "journald"}))
    code = DAEMON_SNIPPET.replace("/etc/docker/daemon.json", str(daemon))
    import subprocess
    import sys
    first = subprocess.run([sys.executable, "-c", code, "10.0.0.5:5000"], capture_output=True, text=True, check=True)
    assert "changed" in first.stdout
    assert json.loads(daemon.read_text()) == {"log-driver": "journald", "insecure-registries": ["10.0.0.5:5000"]}
    second = subprocess.run([sys.executable, "-c", code, "10.0.0.5:5000"], capture_output=True, text=True, check=True)
    assert "changed" not in second.stdout


def test_k3s_registries_yaml():
    f = generate(project("zot", "10.0.0.5:5000", "kubernetes", "k3s", "helm"), CATALOG).files
    data = yaml.safe_load(f["deploy/registries.yaml"])
    assert data == {"mirrors": {"10.0.0.5:5000": {"endpoint": ["http://10.0.0.5:5000"]}}}


def test_registre_avec_nom_dns_inchange():
    f = generate(project("distribution", "registry.example.com", "kubernetes", "k3s", "helm"), CATALOG).files
    assert "deploy/registries.yaml" not in f


def test_note_pour_la_ci():
    r = generate(project("distribution", "192.168.1.20:5000"), CATALOG)
    assert any("HTTP simple" in n and "buildkitd.toml" in n for n in r.ir.notes)


def test_avertissement_ip_sur_une_adresse_d_entree():
    p = Project(name="t", target="docker-host")
    p.add("grafana", CATALOG["grafana"].stage, hostname="192.168.1.20")
    assert "R56" in {d.rule_id for d in ENGINE.evaluate(p)}


def test_pas_d_avertissement_avec_un_nom_nip_io():
    p = Project(name="t", target="docker-host")
    p.add("grafana", CATALOG["grafana"].stage, hostname="grafana.192.168.1.20.nip.io")
    assert "R56" not in {d.rule_id for d in ENGINE.evaluate(p)}


def test_registre_en_ip_sans_avertissement_r56():
    p = project("distribution", "192.168.1.20:5000")
    assert "R56" not in {d.rule_id for d in ENGINE.evaluate(p)}
