# SPDX-License-Identifier: Apache-2.0
"""1.1 : capacité « DNS » — zone et enregistrements vers le répartiteur ou les machines de la pile."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.compat import adapted
from devops_builder.generators import dns, generate
from devops_builder.params import check_value
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
CLOUDS = ["aws", "gcp", "azure", "scaleway"]


def make(cloud: str, hosting: str = "vm", balancer: bool = True, **kw):
    p = build_starter(StarterAnswers(forge="gitlab", hosting=hosting, cloud=cloud, envs="dev-recette-prod",
                                     shared_host=hosting == "vm"), CATALOG)
    if balancer:
        p.add(CATALOG[cloud].services["load-balancer"], "infrastructure")
    p.add(CATALOG[cloud].services["dns"], "infrastructure", **{"zone": "boutique.fr", "record": "boutique", **kw})
    return p


def result(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True)


def main(p) -> str:
    return result(p).files["infra/terraform/main.tf"]


def test_seuls_quatre_clouds_ont_un_dns():
    assert set(dns.DNS) == {CATALOG[c].services["dns"] for c in CLOUDS}
    assert not CATALOG["ovhcloud"].services.get("dns") and not CATALOG["outscale"].services.get("dns")
    for tool_id, cloud in dns.DNS.items():
        assert CATALOG[tool_id].provider == cloud and "dns" in CATALOG[tool_id].provides


RECORD = {"aws": 'resource "aws_route53_record" "', "gcp": 'resource "google_dns_record_set" "',
          "azure": 'resource "azurerm_dns_a_record" "', "scaleway": 'resource "scaleway_domain_record" "'}


@pytest.mark.parametrize("cloud", CLOUDS)
def test_un_enregistrement_par_groupe_de_machines(cloud):
    p = make(cloud)
    m = main(p)
    groups = m.count(RECORD[cloud])
    assert groups >= 2                                          # production + hors production
    assert "boutique.fr" in m and "boutique" in m
    assert RECORD[cloud] not in main(build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud=cloud,
                                                                 envs="dev-recette-prod", shared_host=True), CATALOG))


def test_le_groupe_de_production_porte_le_nom_choisi_les_autres_un_suffixe():
    names = re.findall(r'name    = "([^"]+)"\n  type', main(make("aws", record="www")))
    assert names.count("www.boutique.fr") == 1 and len(names) >= 2
    assert all(n.startswith("www-") and n.endswith(".boutique.fr") for n in names if n != "www.boutique.fr")


def test_vers_le_repartiteur_si_present_sinon_vers_les_machines():
    assert "alias {" in main(make("aws")) and "aws_lb.production.dns_name" in main(make("aws"))
    assert "alias {" not in main(make("aws", balancer=False))
    assert "aws_instance.production[*].public_ip" in main(make("aws", balancer=False))
    assert "google_compute_address.lb_production.address" in main(make("gcp"))
    assert "azurerm_public_ip.lb_production.ip_address" in main(make("azure"))
    assert "scaleway_lb_ip.production.ip_address" in main(make("scaleway"))
    assert "tolist(scaleway_instance_ip.production[*].address)[0]" in main(make("scaleway", balancer=False))


def test_zone_creee_sauf_chez_scaleway_et_serveurs_de_noms_en_sortie():
    for cloud, zone in (("aws", "aws_route53_zone"), ("gcp", "google_dns_managed_zone"), ("azure", "azurerm_dns_zone")):
        r = result(make(cloud))
        assert f'resource "{zone}" "main"' in r.files["infra/terraform/main.tf"]
        assert "dns_name_servers" in r.files["infra/terraform/outputs.tf"]
        assert any("serveurs de noms" in n for n in r.ir.notes)
    sw = result(make("scaleway"))
    assert "scaleway_domain_zone" not in sw.files["infra/terraform/main.tf"]
    assert any("déjà être géré par Scaleway" in n for n in sw.ir.notes)


def test_sur_kubernetes_la_zone_seule_et_une_note():
    r = result(make("aws", "kubernetes-managed", balancer=False))
    m = r.files["infra/terraform/main.tf"]
    assert 'resource "aws_route53_zone" "main"' in m and "aws_route53_record" not in m
    assert any("external-dns" in n for n in r.ir.notes)


def test_domaine_invalide_refuse_et_exemple_signale():
    spec = CATALOG["aws-route53"].param_schema["zone"]
    for bad in ("https://boutique.fr", "boutique", "boutique.fr.", "Boutique.fr"):
        assert check_value(spec, bad), bad
    assert not check_value(spec, "mon-site.example.fr")
    p = make("aws", zone="exemple.fr")
    assert "R34" in {d.rule_id for d in ENGINE.evaluate(p)}


def test_la_palette_ne_propose_que_le_dns_du_cloud_du_projet():
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud="aws", envs="prod"), CATALOG)
    keep, reasons = adapted([CATALOG[t] for t in dns.DNS], p, CATALOG)
    assert [t.id for t in keep] == ["aws-route53"] and set(reasons) == set(dns.DNS) - {"aws-route53"}


@pytest.mark.skipif(not shutil.which("tofu"), reason="tofu absent")
@pytest.mark.parametrize("cloud", CLOUDS)
def test_pile_dns_conforme_a_tofu_fmt(cloud, tmp_path):
    for balancer in (True, False):
        files = result(make(cloud, balancer=balancer)).files
        d = tmp_path / str(balancer)
        d.mkdir()
        for name, content in files.items():
            if name.startswith("infra/terraform/"):
                (d / name.rsplit("/", 1)[1]).write_text(content)
        r = subprocess.run(["tofu", "fmt", "-check", "-diff", "-no-color", str(d)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
