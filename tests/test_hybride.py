# SPDX-License-Identifier: Apache-2.0
"""Hébergement par environnement : développement sur un hôte Docker, recette et production sur Kubernetes."""

from __future__ import annotations

import yaml
from test_data import CATALOG, ENGINE, files_of, project

from devops_builder.comparaison import compare
from devops_builder.generators import generate
from devops_builder.model import Project
from devops_builder.ports import compose_publishes, parametrized, port_plan

TOOLS = ("github", "github-actions", "buildkit", "ghcr", "docker-compose", "k3s", "helm")


def hybrid(envs: str = "dev-staging-prod") -> Project:
    p = project("kubernetes", *TOOLS, envs=envs)
    p.environments[0].target = "docker-host"
    p.environments[0].host = "vm-dev"
    return p


def rules(p: Project) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in ENGINE.evaluate(p):
        out[d.rule_id] = f"{out[d.rule_id]} {d.message}" if d.rule_id in out else d.message
    return out


def test_format_et_aller_retour():
    p = hybrid()
    assert "target: docker-host" in p.to_yaml()
    assert "target:" not in project("kubernetes", *TOOLS).to_yaml().replace("target: kubernetes", "")
    back = Project.from_yaml(p.to_yaml())
    assert [e.target for e in back.environments] == ["docker-host", "", ""] and back.hybrid
    assert not project("kubernetes", *TOOLS).hybrid and back.env_target(back.environments[1]) == "kubernetes"


def test_une_etape_de_deploiement_par_hebergement():
    text = files_of(hybrid())[".github/workflows/pipeline.yml"]
    flow = yaml.safe_load(text)
    dev, staging = flow["jobs"]["deploy-dev"], flow["jobs"]["deploy-staging"]
    body = lambda job: "\n".join(str(s.get("run", "")) for s in job["steps"])  # noqa: E731
    assert "docker compose" in body(dev) and "helm" not in body(dev) and "DEPLOY_HOST_DEV" in body(dev)
    assert "helm upgrade" in body(staging) and "docker compose" not in body(staging)
    assert "needs" in staging and "deploy-dev" in staging["needs"]


def test_ports_par_environnement():
    entries = port_plan(hybrid(), CATALOG)
    by_env = {}
    for e in entries:
        by_env.setdefault(e.env_id, []).append(e)
    assert any(e.host_port is not None for e in by_env["dev"])           # hôte Docker : port publié
    assert all(e.host_port is None for e in by_env["staging"] + by_env["production"])
    assert "Service" in next(e for e in by_env["production"] if e.component_id == "app").exposure


def test_compose_publishes_par_environnement():
    p = hybrid()
    assert compose_publishes(p, p.environments[0]) and not compose_publishes(p, p.environments[2])
    assert compose_publishes(p) and not parametrized(p)


def test_fichiers_env_seulement_pour_les_hotes():
    p = hybrid()
    p.environments[0].port_offset = 1000
    files = files_of(p)
    assert "deploy/env/dev.env" in files and "deploy/env/production.env" not in files


def test_r61_briques_manquantes():
    p = hybrid()
    assert "R61" not in rules(p)
    for tool in ("docker-compose",):
        q = hybrid()
        q.stages = {s: [b for b in bricks if b.tool != tool] for s, bricks in q.stages.items()}
        assert "Docker Compose" in rules(q)["R61"]
    q = hybrid()
    q.target = "docker-host"
    q.environments[1].target = "kubernetes-managed"
    q.stages = {s: [b for b in bricks if b.tool not in ("k3s", "helm")] for s, bricks in q.stages.items()}
    message = rules(q)["R61"]
    assert "ajouter un cluster" in message and "Helm ou Kustomize" in message


def test_r61_hebergement_inconnu():
    p = hybrid()
    p.environments[1].target = "mainframe"
    assert "inconnu" in rules(p)["R61"]


def test_r61_base_de_donnees_en_hybride_avertit():
    p = project("kubernetes", *TOOLS, "postgresql")
    p.environments[0].target = "docker-host"
    found = {d.rule_id: d for d in ENGINE.evaluate(p)}
    assert found["R61"].severity.value in ("avertissement", "warning") or "base de données" in found["R61"].message


def test_rapport_et_comparaison():
    p = hybrid()
    report = generate(p, CATALOG, ENGINE, allow_blocking=True).files["PIPELINE.md"]
    assert "| Environnement | Type | Hébergement |" in report and "Hôte Docker unique" in report
    plain = generate(project("kubernetes", *TOOLS), CATALOG, ENGINE, allow_blocking=True).files["PIPELINE.md"]
    assert "Hébergement |" not in plain
    cmp = compare(project("kubernetes", *TOOLS, envs="dev-staging-prod"), p, CATALOG, ENGINE)
    assert any("hébergement" in line for line in cmp.environments)


def test_exemple_sans_diagnostic():
    from pathlib import Path
    path = Path(__file__).parents[1] / "devops_builder" / "data" / "examples" / "07-hybride-hote-kubernetes.devops.yaml"
    p = Project.load(path)
    assert p.hybrid and not ENGINE.evaluate(p)
