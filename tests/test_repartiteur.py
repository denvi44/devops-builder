# SPDX-License-Identifier: Apache-2.0
"""1.1 : capacité « répartiteur de charge » — une brique par cloud, devant les machines de la pile."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.compat import adapted
from devops_builder.generators import generate, lb
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
CLOUDS = ["aws", "gcp", "azure", "scaleway", "ovhcloud", "outscale"]


def make(cloud: str, hosting: str = "vm", net: bool = True, balancer: bool = True, **kw):
    a = StarterAnswers(forge="gitlab", hosting=hosting, cloud=cloud, envs="dev-recette-prod", shared_host=hosting == "vm",
                       secnumcloud=cloud == "outscale", **kw)
    p = build_starter(a, CATALOG)
    if net:
        p.add(CATALOG[cloud].services["network"], "infrastructure")
    if balancer:
        p.add(CATALOG[cloud].services["load-balancer"], "infrastructure")
    return p


def result(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True)


def tf(p, name="main.tf") -> str:
    return result(p).files[f"infra/terraform/{name}"]


def test_chaque_fournisseur_declare_son_repartiteur():
    assert set(lb.LB) == {CATALOG[c].services["load-balancer"] for c in CLOUDS}
    for tool_id, cloud in lb.LB.items():
        assert CATALOG[tool_id].provider == cloud and "load-balancer" in CATALOG[tool_id].provides


EXPECTED = {"aws": 'resource "aws_lb" "', "gcp": 'resource "google_compute_forwarding_rule" "',
            "azure": 'resource "azurerm_lb" "', "scaleway": 'resource "scaleway_lb" "',
            "ovhcloud": 'resource "ovh_cloud_loadbalancer" "', "outscale": 'resource "outscale_load_balancer" "'}


@pytest.mark.parametrize("cloud", CLOUDS)
def test_un_repartiteur_par_groupe_de_machines_et_sa_sortie(cloud):
    p = make(cloud)
    main, outputs = tf(p), tf(p, "outputs.tf")
    groups = re.findall(r'output "lb_(\w+)"', outputs)
    assert groups and main.count(EXPECTED[cloud]) == len(groups)
    assert EXPECTED[cloud] not in tf(make(cloud, balancer=False))


def test_ports_web_et_sonde_tcp():
    main = tf(make("aws"))
    assert 'protocol = "TCP"' in main and "port     = \"80\"" in main
    assert 'resource "aws_lb_listener" "' in main and main.count("protocol          = \"TCP\"") >= 2
    traefik = tf(make("scaleway"))
    assert "inbound_port = 80" in traefik and "inbound_port = 443" in traefik and "health_check_tcp" in traefik


def test_aws_reseau_du_projet_ou_reseau_par_defaut():
    avec = tf(make("aws"))
    assert "subnets            = aws_subnet.public[*].id" in avec and "data.aws_vpc.default" not in avec
    sans = tf(make("aws", net=False))
    assert "data.aws_subnets.default.ids" in sans and 'data "aws_vpc" "default"' in sans


def test_outscale_dans_le_net_ou_en_sous_region():
    avec = tf(make("outscale"))
    assert "internet-facing" in avec and "outscale_subnet.main.subnet_id" in avec
    sans = tf(make("outscale", net=False))
    assert "subregion_names" in sans and "internet-facing" not in sans


def test_ovhcloud_demande_un_reseau_prive():
    p = make("ovhcloud", net=False)
    assert "R29" in {d.rule_id for d in ENGINE.evaluate(p)}
    ok = make("ovhcloud")
    assert "R29" not in {d.rule_id for d in ENGINE.evaluate(ok)}
    assert any("pool_member" in n for n in result(ok).ir.notes)


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_sur_kubernetes_aucune_ressource_et_une_note(cloud):
    p = make(cloud, "kubernetes-managed", net=False)
    r = result(p)
    assert EXPECTED[cloud] not in r.files["infra/terraform/main.tf"]
    assert any("Service de type LoadBalancer" in n for n in r.ir.notes)


def test_la_palette_ne_propose_que_le_repartiteur_du_cloud_du_projet():
    p = make("aws", net=False, balancer=False)
    keep, reasons = adapted([CATALOG[t] for t in lb.LB], p, CATALOG)
    assert [t.id for t in keep] == ["aws-elb"] and set(reasons) == set(lb.LB) - {"aws-elb"}


@pytest.mark.skipif(not shutil.which("tofu"), reason="tofu absent")
@pytest.mark.parametrize("cloud", CLOUDS)
def test_pile_repartiteur_conforme_a_tofu_fmt(cloud, tmp_path):
    for net in (True, False):
        if cloud == "ovhcloud" and not net:
            continue
        files = result(make(cloud, net=net)).files
        d = tmp_path / str(net)
        d.mkdir()
        for name, content in files.items():
            if name.startswith("infra/terraform/"):
                (d / name.rsplit("/", 1)[1]).write_text(content)
        r = subprocess.run(["tofu", "fmt", "-check", "-diff", "-no-color", str(d)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
