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
WEB = ("grafana", "sonarqube", "jenkins", "gitea", "zot", "harbor", "argo-cd", "argo-workflows", "chaos-mesh")
AVEC_MANIFESTE = ("jaeger",)   # Ingress écrit dans platform/ingress.yaml, pas dans les valeurs du chart
CLASSES = {"traefik": "traefik", "ingress-nginx": "nginx"}


def kube(ingress: str, deploy: str = "helm") -> Project:
    p = Project(name="t", target="kubernetes", environments=env_preset("staging-prod"))
    for t in dict.fromkeys(("gitlab", "gitlab-ci", "buildkit", deploy, "k3s", ingress, *WEB, *AVEC_MANIFESTE)):
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
                           ("gitea", f"ingress.className={cls}"), ("zot", f"ingress.className={cls}"),
                           ("harbor", f"expose.ingress.className={cls}"),
                           ("argo-cd", f"server.ingress.ingressClassName={cls}"),
                           ("argo-workflows", f"server.ingress.ingressClassName={cls}"),
                           ("chaos-mesh", f"dashboard.ingress.ingressClassName={cls}")):
        line = next(ln for ln in install.splitlines() if ln.startswith(f"helm upgrade --install {tool} "))
        assert expected in line, tool
    assert "grafana.example.com" in install and "registry.example.com" in install
    assert "argocd.example.com" in install and "chaos.example.com" in install
    assert "configs.params.server.insecure=true" in install, "Argo CD derrière l'entrée parle en clair"
    ingress_file = list(yaml.safe_load_all(files(kube(ingress))["platform/ingress.yaml"]))
    assert [d["metadata"]["name"] for d in ingress_file] == ["jaeger"] and ingress_file[0]["spec"]["ingressClassName"] == cls
    assert 'kubectl apply -f "$(dirname "$0")/ingress.yaml"' in install


def test_gateway_api_pour_les_briques_avec_envoy_gateway():
    f = files(kube("envoy-gateway"))
    docs = list(yaml.safe_load_all(f["platform/gateway.yaml"]))
    assert [d["kind"] for d in docs[:2]] == ["GatewayClass", "Gateway"]
    routes = {d["metadata"]["name"]: d for d in docs if d["kind"] == "HTTPRoute"}
    assert set(routes) == {*WEB, *AVEC_MANIFESTE}
    assert "platform/ingress.yaml" not in f
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
    for tool in (*WEB, *AVEC_MANIFESTE):
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


# ------------------------------------------------------------------ HTTPS (cert-manager)
def avec_https(ingress: str, deploy: str = "helm") -> Project:
    p = kube(ingress, deploy)
    p.add("cert-manager", CATALOG["cert-manager"].stage)
    return p


@pytest.mark.parametrize("ingress", ["traefik", "ingress-nginx"])
def test_https_application_et_briques_par_cert_manager(ingress):
    f = files(avec_https(ingress))
    assert yaml.safe_load(f["charts/mon-app/values.yaml"])["ingress"]["clusterIssuer"] == "letsencrypt"
    assert "cert-manager.io/cluster-issuer" in f["charts/mon-app/templates/ingress.yaml"]
    install = f["platform/install.sh"]
    for tool in ("grafana", "sonarqube", "jenkins", "gitea", "zot", "argo-workflows"):
        line = next(ln for ln in install.splitlines() if ln.startswith(f"helm upgrade --install {tool} "))
        assert "cert-manager\\.io/cluster-issuer=letsencrypt" in line and f"{tool}-tls" in line, tool
    assert "server.ingress.tls=true" in install and "expose.tls.secret.secretName=harbor-tls" in install
    issuer = yaml.safe_load(f["platform/cluster-issuer.yaml"])
    solver = issuer["spec"]["acme"]["solvers"][0]["http01"]["ingress"]
    assert issuer["kind"] == "ClusterIssuer" and solver["ingressClassName"] == CLASSES[ingress]
    jaeger = yaml.safe_load(f["platform/ingress.yaml"])
    assert jaeger["spec"]["tls"][0]["secretName"] == "jaeger-tls"
    assert install.index("helm upgrade --install cert-manager") < install.index('cluster-issuer.yaml"')
    assert " --wait" in next(ln for ln in install.splitlines() if "install cert-manager " in ln)


def test_https_overlay_kustomize():
    f = files(avec_https("ingress-nginx", "kustomize"))
    ing = yaml.safe_load(f["deploy/kustomize/overlays/production/ingress.yaml"])
    assert ing["metadata"]["annotations"] == {"cert-manager.io/cluster-issuer": "letsencrypt"}
    assert ing["spec"]["tls"] == [{"hosts": ["mon-app.example.com"], "secretName": "mon-app-tls"}]


def test_https_envoy_gateway_un_listener_par_nom_d_hote():
    f = files(avec_https("envoy-gateway"))
    docs = list(yaml.safe_load_all(f["platform/gateway.yaml"]))
    gateway = docs[1]
    assert gateway["metadata"]["annotations"]["cert-manager.io/cluster-issuer"] == "letsencrypt"
    https = {li["hostname"]: li for li in gateway["spec"]["listeners"] if li["protocol"] == "HTTPS"}
    assert {"mon-app.example.com", "staging.mon-app.example.com", "grafana.example.com", "harbor.example.com"} <= set(https)
    assert all(li["tls"]["mode"] == "Terminate" for li in https.values())
    names = [li["name"] for li in gateway["spec"]["listeners"]]
    assert len(names) == len(set(names)) and all(len(n) <= 63 for n in names)
    issuer = yaml.safe_load(f["platform/cluster-issuer.yaml"])
    assert "gatewayHTTPRoute" in issuer["spec"]["acme"]["solvers"][0]["http01"]
    cm = next(ln for ln in f["platform/install.sh"].splitlines() if "install cert-manager " in ln)
    assert "config.enableGatewayAPI=true" in cm


def test_email_du_compte_acme():
    p = avec_https("traefik")
    next(b for _, b in p.all_bricks() if b.tool == "traefik").params["acme_email"] = "ops@boutique.fr"
    assert yaml.safe_load(files(p)["platform/cluster-issuer.yaml"])["spec"]["acme"]["email"] == "ops@boutique.fr"
    assert "email" not in yaml.safe_load(files(avec_https("ingress-nginx"))["platform/cluster-issuer.yaml"])["spec"]["acme"]


def test_sans_cert_manager_rien_de_https():
    f = files(kube("ingress-nginx"))
    assert "clusterIssuer" not in f["charts/mon-app/values.yaml"]
    assert "platform/cluster-issuer.yaml" not in f and "cert-manager" not in f["platform/install.sh"]


def test_regle_entree_sans_cert_manager():
    p = kube("ingress-nginx")
    diags = [d for d in ENGINE.evaluate(p) if d.rule_id == "R54"]
    assert diags and diags[0].actions and diags[0].actions[0].args["tool"] == "cert-manager"
    assert not [d for d in ENGINE.evaluate(avec_https("ingress-nginx")) if d.rule_id == "R54"]
