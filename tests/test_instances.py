# SPDX-License-Identifier: Apache-2.0
"""0.21 : plusieurs instances nommées d'un même outil (deux Grafana, deux Gitea…)."""

from __future__ import annotations

import pytest
import yaml

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.instances import check_name, suggest_name
from devops_builder.model import Project, Severity, env_preset
from devops_builder.network import build_graph
from devops_builder.ports import port_plan
from devops_builder.rules import RuleEngine

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)


def compose(traefik: bool = True) -> Project:
    p = Project(name="t", target="docker-host", environments=env_preset("staging-prod"))
    tools = ["gitlab", "gitlab-ci", "buildkit", "docker-compose", "grafana", "gitea"] + (["traefik"] if traefik else [])
    for t in tools:
        p.add(t, CATALOG[t].stage)
    p.add("grafana", CATALOG["grafana"].stage, instance="equipe-b")
    p.add("gitea", CATALOG["gitea"].stage, instance="2")
    return p


def services(p: Project) -> dict:
    f = generate(p, CATALOG).files
    return yaml.safe_load(f["deploy/docker-compose.yml"])["services"]


def rules(p: Project) -> dict[str, Severity]:
    return {d.rule_id: d.severity for d in ENGINE.evaluate(p)}


def test_identifiants_de_service():
    p = compose()
    assert [b.service_id for b in p.bricks_for("grafana")] == ["grafana", "grafana-equipe-b"]
    assert [b.service_id for b in p.bricks_for("gitea")] == ["gitea", "gitea-2"]


def test_services_et_volumes_distincts():
    s = services(compose())
    assert {"grafana", "grafana-equipe-b", "gitea", "gitea-2"} <= set(s)
    assert s["grafana"]["volumes"] != s["grafana-equipe-b"]["volumes"]
    assert any("grafana-data-equipe-b" in v for v in s["grafana-equipe-b"]["volumes"])


def test_routeurs_traefik_par_instance():
    s = services(compose())
    labels = " ".join(map(str, s["grafana-equipe-b"]["labels"]))
    assert "Host(`grafana-equipe-b.example.com`)" in labels
    assert "grafana-equipe-b.example.com" not in " ".join(map(str, s["grafana"]["labels"]))


def test_ports_decales_sans_entree():
    plan = [e for e in port_plan(compose(traefik=False), CATALOG) if e.tool_id in ("grafana", "gitea")]
    env = plan[0].env_id
    ports = [e.host_port for e in plan if e.host_port and e.env_id == env]
    assert len(ports) == len(set(ports))   # aucune collision entre instances
    assert not any(d.rule_id == "R39" for d in ENGINE.evaluate(compose(traefik=False)))


def test_noeuds_du_schema_reseau():
    p = compose()
    g = build_graph(p, CATALOG, ENGINE)
    ids = {n.id: n.label for n in g.nodes}
    assert ids["grafana-equipe-b"] == "Grafana (equipe-b)"
    assert "gitea-2" in ids


def test_instances_valides_sans_avertissement():
    assert "R55" not in rules(compose())


def test_nom_invalide_bloque():
    p = compose()
    p.bricks_for("grafana")[1].instance = "Équipe B!"
    assert rules(p)["R55"] is Severity.BLOCKING


def test_outil_non_multi_refuse_en_double():
    p = compose()
    p.add("docker-compose", CATALOG["docker-compose"].stage)
    assert "R55" in rules(p)


def test_doublon_de_nom_signale():
    p = compose()
    p.bricks_for("grafana")[1].instance = ""
    assert rules(p)["R55"] is Severity.WARNING


@pytest.mark.parametrize("name,ok", [("equipe-b", True), ("2", True), ("", True), ("-x", False), ("A", False),
                                     ("a" * 31, False), ("x_y", False)])
def test_check_name(name, ok):
    assert (check_name(name) is None) is ok


def test_suggest_name():
    p = compose()
    assert suggest_name(p, "gitea") == "3"
    assert suggest_name(p, "grafana") == "2"


def kube(ingress: str = "traefik") -> Project:
    p = Project(name="t", target="kubernetes", environments=env_preset("staging-prod"))
    for t in ("gitlab", "gitlab-ci", "buildkit", "helm", "k3s", ingress, "grafana", "gitea", "jaeger", "cert-manager"):
        p.add(t, CATALOG[t].stage)
    for t, name in (("grafana", "equipe-b"), ("gitea", "2"), ("jaeger", "perf")):
        p.add(t, CATALOG[t].stage, instance=name)
    return p


def install(p: Project) -> list[str]:
    return generate(p, CATALOG).files["platform/install.sh"].splitlines()


def test_helm_une_release_par_instance():
    lines = install(kube())
    releases = [ln.split()[3] for ln in lines if ln.startswith("helm upgrade --install")]
    assert {"grafana", "grafana-equipe-b", "gitea", "gitea-2"} <= set(releases)
    b = next(ln for ln in lines if ln.startswith("helm upgrade --install grafana-equipe-b "))
    assert "--namespace monitoring-equipe-b" in b or "-equipe-b" in b.split("--namespace")[1].split()[0]
    assert "grafana-equipe-b.example.com" in b
    assert "grafana.example.com" in next(ln for ln in lines if ln.startswith("helm upgrade --install grafana "))


def test_helm_https_par_instance():
    b = next(ln for ln in install(kube()) if ln.startswith("helm upgrade --install grafana-equipe-b "))
    assert "grafana-equipe-b-tls" in b


def test_ingress_manifeste_par_instance():
    f = generate(kube(), CATALOG).files
    docs = list(yaml.safe_load_all(f["platform/ingress.yaml"]))
    by_name = {d["metadata"]["name"]: d for d in docs}
    assert {"jaeger", "jaeger-perf"} <= set(by_name)
    assert by_name["jaeger-perf"]["metadata"]["namespace"] != by_name["jaeger"]["metadata"]["namespace"]
    assert by_name["jaeger-perf"]["spec"]["rules"][0]["host"] == "jaeger-perf.example.com"
    assert by_name["jaeger-perf"]["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["name"] == "jaeger-perf"


def test_gateway_routes_par_instance():
    f = generate(kube("envoy-gateway"), CATALOG).files
    docs = list(yaml.safe_load_all(f["platform/gateway.yaml"]))
    routes = {d["metadata"]["name"]: d for d in docs if d["kind"] == "HTTPRoute"}
    assert {"grafana", "grafana-equipe-b", "gitea-2"} <= set(routes)
    assert routes["grafana-equipe-b"]["spec"]["hostnames"] == ["grafana-equipe-b.example.com"]
    gateway = next(d for d in docs if d["kind"] == "Gateway")
    assert any(ln.get("hostname") == "grafana-equipe-b.example.com" for ln in gateway["spec"]["listeners"])
