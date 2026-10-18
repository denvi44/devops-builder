# SPDX-License-Identifier: Apache-2.0
"""0.21 : l'entrée (Traefik, ingress-nginx, Envoy Gateway) route l'application et les interfaces web des briques."""

from __future__ import annotations

import pytest
import yaml

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.model import Project, env_preset
from devops_builder.network import build_graph
from devops_builder.rules import RuleEngine

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
WEB = ("grafana", "sonarqube", "jenkins", "gitea", "zot")
CLASSES = {"traefik": "traefik", "ingress-nginx": "nginx"}


def kube(ingress: str, deploy: str = "helm") -> Project:
    p = Project(name="t", target="kubernetes", environments=env_preset("staging-prod"))
    for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", deploy, "k3s", ingress, *WEB):
        p.add(t, CATALOG[t].stage)
    return p


def files(p: Project) -> dict[str, str]:
    return generate(p, CATALOG).files


@pytest.mark.parametrize("ingress", ["traefik", "ingress-nginx"])
def test_ingress_de_l_application_dans_le_chart(ingress):
    f = files(kube(ingress))
    values = yaml.safe_load(f["charts/mon-app/values.yaml"])
    assert values["ingress"] == {"enabled": True, "className": CLASSES[ingress], "host": "mon-app.example.com"}
    assert yaml.safe_load(f["charts/mon-app/values-staging.yaml"])["ingress"]["host"] == "staging.mon-app.example.com"
    assert "kind: Ingress" in f["charts/mon-app/templates/ingress.yaml"]
    assert "charts/mon-app/templates/httproute.yaml" not in f


def test_httproute_de_l_application_avec_envoy_gateway():
    f = files(kube("envoy-gateway"))
    assert yaml.safe_load(f["charts/mon-app/values.yaml"])["ingress"] == {"enabled": True, "host": "mon-app.example.com"}
    assert "kind: HTTPRoute" in f["charts/mon-app/templates/httproute.yaml"]
    assert "charts/mon-app/templates/ingress.yaml" not in f


@pytest.mark.parametrize("ingress", ["traefik", "ingress-nginx", "envoy-gateway"])
def test_overlays_kustomize(ingress):
    f = files(kube(ingress, "kustomize"))
    kind = "HTTPRoute" if ingress == "envoy-gateway" else "Ingress"
    staging = yaml.safe_load(f["deploy/kustomize/overlays/staging/ingress.yaml"])
    assert staging["kind"] == kind
    assert "staging.mon-app.example.com" in str(staging)
    assert "ingress.yaml" in yaml.safe_load(f["deploy/kustomize/overlays/production/kustomization.yaml"])["resources"]


@pytest.mark.parametrize("ingress", ["traefik", "ingress-nginx"])
def test_interfaces_web_des_briques_derriere_le_controleur(ingress):
    install = files(kube(ingress))["platform/install.sh"]
    cls = CLASSES[ingress]
    for tool, expected in (("grafana", f"ingress.ingressClassName={cls}"), ("sonarqube", f"ingress.ingressClassName={cls}"),
                           ("jenkins", f"controller.ingress.ingressClassName={cls}"),
                           ("gitea", f"ingress.className={cls}"), ("zot", f"ingress.className={cls}")):
        line = next(ln for ln in install.splitlines() if ln.startswith(f"helm upgrade --install {tool} "))
        assert expected in line, tool
    assert "grafana.example.com" in install and "registry.example.com" in install


def test_gateway_api_pour_les_briques_avec_envoy_gateway():
    f = files(kube("envoy-gateway"))
    docs = list(yaml.safe_load_all(f["platform/gateway.yaml"]))
    assert [d["kind"] for d in docs[:2]] == ["GatewayClass", "Gateway"]
    routes = {d["metadata"]["name"]: d for d in docs if d["kind"] == "HTTPRoute"}
    assert set(routes) == set(WEB)
    assert routes["grafana"]["metadata"]["namespace"] == "monitoring"
    assert routes["grafana"]["spec"]["hostnames"] == ["grafana.example.com"]
    install = f["platform/install.sh"]
    assert install.index("helm upgrade --install gitea") < install.index("kubectl apply -f")
    assert "--set ingress.enabled" not in install, "pas d'Ingress avec la Gateway API"


@pytest.mark.parametrize("ingress", ["traefik", "ingress-nginx", "envoy-gateway"])
def test_vue_reseau_derriere_l_entree(ingress):
    g = build_graph(kube(ingress), CATALOG, ENGINE)
    edges = {(e.src, e.dst) for e in g.edges}
    assert ("internet", ingress) in edges and (ingress, "app") in edges
    for tool in WEB:
        assert (ingress, tool) in edges, tool
        assert not any(e.public and e.dst == tool for e in g.edges)


def test_nom_d_hote_choisi_sur_la_brique():
    p = kube("ingress-nginx")
    next(b for _, b in p.all_bricks() if b.tool == "grafana").params["hostname"] = "metrics.boutique.fr"
    next(b for _, b in p.all_bricks() if b.tool == "ingress-nginx").params["app_hostname"] = "boutique.fr"
    f = files(p)
    assert "metrics.boutique.fr" in f["platform/install.sh"]
    assert yaml.safe_load(f["charts/mon-app/values.yaml"])["ingress"]["host"] == "boutique.fr"


def test_pas_de_controleur_pas_d_ingress():
    p = Project(name="t", target="kubernetes", environments=env_preset("prod"))
    for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", "helm", "grafana"):
        p.add(t, CATALOG[t].stage)
    f = files(p)
    assert not any("ingress" in k or "httproute" in k for k in f)
    assert "ingress.enabled" not in f["platform/install.sh"]


def test_controleur_kubernetes_refuse_sur_hote_docker():
    p = Project(name="t", target="docker-host", environments=env_preset("prod"))
    for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", "docker-compose", "ingress-nginx"):
        p.add(t, CATALOG[t].stage)
    assert any(d.rule_id == "R01" and d.severity.name == "BLOCKING" for d in ENGINE.evaluate(p))
