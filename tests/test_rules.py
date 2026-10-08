"""Un test par règle de la matrice (R00 à R24), plus les corrections."""

from __future__ import annotations

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.model import Project, Severity
from devops_builder.rules import RuleEngine, apply_action, load_rules

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)


def make(target: str = "kubernetes", env: str = "production", **flags) -> Project:
    p = Project(name="test", target=target, environment=env)
    for k, v in flags.items():
        setattr(p, k, v)
    return p


def put(p: Project, *tool_ids: str) -> Project:
    for tid in tool_ids:
        p.add(tid, CATALOG[tid].stage)
    return p


def ids(p: Project) -> dict[str, Severity]:
    return {d.rule_id: d.severity for d in ENGINE.evaluate(p)}


# (règle, projet qui la déclenche, gravité attendue)
CASES = [
    ("R00", lambda: put(make(), "lsc-backstage" if "lsc-backstage" in CATALOG else next(
        t.id for t in CATALOG.tools.values() if not t.curated)), Severity.INFO),
    ("R01", lambda: put(make("docker-host"), "argo-cd"), Severity.BLOCKING),
    ("R02", lambda: put(make(), "argo-cd", "flux"), Severity.BLOCKING),
    ("R03", lambda: put(make(), "istio", "linkerd"), Severity.BLOCKING),
    ("R04", lambda: put(make(), "cilium", "calico"), Severity.BLOCKING),
    ("R05", lambda: put(make("kubernetes-managed"), "aws", "eks", "k3s"), Severity.BLOCKING),
    ("R06", lambda: put(make(), "gitlab", "github-actions"), Severity.BLOCKING),
    ("R07", lambda: put(make(), "thanos"), Severity.BLOCKING),
    ("R08", lambda: put(make(), "velero"), Severity.BLOCKING),
    ("R09", lambda: put(make(), "ecr"), Severity.BLOCKING),
    ("R10", lambda: put(make(), "aws", "app-mesh"), Severity.BLOCKING),
    ("R11", lambda: put(make(), "gcp", "gcr"), Severity.BLOCKING),
    ("R12", lambda: put(make(secnumcloud=True), "aws", "eks"), Severity.BLOCKING),
    ("R13", lambda: put(make(), "ingress-nginx"), Severity.WARNING),
    ("R14", lambda: put(make(), "kaniko"), Severity.WARNING),
    ("R15", lambda: put(make(), "kyverno", "gatekeeper"), Severity.WARNING),
    ("R16", lambda: put(make(), "terraform", "opentofu"), Severity.WARNING),
    ("R17", lambda: put(make("kubernetes"), "docker-compose"), Severity.WARNING),
    ("R18", lambda: put(make("kubernetes", "production"), "kind"), Severity.WARNING),
    ("R19", lambda: put(make(env="production"), "jaeger"), Severity.WARNING),
    ("R20", lambda: put(make("kubernetes-managed"), "aws", "gcp", "eks", "artifact-registry"),
     Severity.WARNING),
    ("R21", lambda: put(make(cloud_auth="static"), "azure"), Severity.WARNING),
    ("R22", lambda: put(make(), "gitea", "github-actions"), Severity.WARNING),
    ("R23", lambda: put(make(), "harbor", "trivy"), Severity.INFO),
    ("R24", lambda: put(make(), "terraform"), Severity.INFO),
]


def test_toutes_les_regles_ont_un_cas():
    assert {r.id for r in load_rules()} == {c[0] for c in CASES}


@pytest.mark.parametrize("rule_id,build,severity", CASES, ids=[c[0] for c in CASES])
def test_regle_declenchee(rule_id, build, severity):
    found = ids(build())
    assert rule_id in found, f"{rule_id} attendu, obtenu {sorted(found)}"
    assert found[rule_id] is severity


@pytest.mark.parametrize("rule_id,build,severity", CASES, ids=[c[0] for c in CASES])
def test_chaque_correction_est_applicable(rule_id, build, severity):
    project = build()
    for diag in ENGINE.evaluate(project):
        for action in diag.actions:
            copy = project.clone()
            apply_action(copy, action, CATALOG)  # ne doit pas lever


def test_pipeline_propre_sans_diagnostic():
    p = put(make("docker-host"), "gitlab", "gitlab-ci", "buildkit", "unit-tests", "trivy",
            "harbor", "opentofu", "ansible", "docker-compose", "traefik", "prometheus", "grafana")
    blocking = [d for d in ENGINE.evaluate(p) if d.severity is Severity.BLOCKING]
    assert blocking == []


def test_r22_ne_bloque_pas_gitea():
    found = ids(put(make(), "gitea", "github-actions"))
    assert "R06" not in found and "R22" in found


def test_r01_resolu_en_ajoutant_k3s():
    p = put(make("vm"), "argo-cd")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R01")
    add_k3s = next(a for a in diag.actions if a.op == "add_brick")
    apply_action(p, add_k3s, CATALOG)
    assert "R01" not in ids(p)


def test_r01_resolu_par_remplacement():
    p = put(make("docker-host"), "argo-cd")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R01")
    swap = next(a for a in diag.actions if a.op == "replace_brick" and a.args["tool"] == "docker-compose")
    apply_action(p, swap, CATALOG)
    assert "argo-cd" not in p.tool_ids() and "docker-compose" in p.tool_ids()
    assert "R01" not in ids(p)


def test_r09_resolu_en_ajoutant_le_fournisseur():
    p = put(make(), "ecr")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R09")
    apply_action(p, diag.actions[0], CATALOG)
    assert "aws" in p.tool_ids() and "R09" not in ids(p)


def test_licence_politique_oss_only_devient_avertissement():
    p = put(make(license_policy="oss-only"), "snyk")
    assert ids(p).get("R24") is Severity.WARNING


def test_ovhcloud_partiel_non_bloque_en_secnumcloud():
    p = put(make("kubernetes-managed", secnumcloud=True), "ovhcloud", "ovh-mks")
    assert "R12" not in ids(p)
