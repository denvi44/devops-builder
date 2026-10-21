# SPDX-License-Identifier: Apache-2.0
"""1.1 : capacité « CDN et pare-feu » — un CDN devant le répartiteur ou les machines, avec un pare-feu applicatif."""

from __future__ import annotations

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.compat import adapted
from devops_builder.generators import cdn, generate
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
CLOUDS = {"aws": "aws-cloudfront", "gcp": "gcp-cdn", "azure": "azure-front-door", "scaleway": "scaleway-edge-services"}
LB = {"aws": "aws-elb", "gcp": "gcp-lb", "azure": "azure-lb", "scaleway": "scaleway-lb"}
CDN_RESOURCE = {"aws": 'resource "aws_cloudfront_distribution" "main"',
                "gcp": 'resource "google_compute_backend_service" "cdn"',
                "azure": 'resource "azurerm_cdn_frontdoor_route" "main"',
                "scaleway": 'resource "scaleway_edge_services_waf_stage" "main"'}
WAF = {"aws": "aws_wafv2_web_acl", "gcp": "google_compute_security_policy",
       "azure": "azurerm_cdn_frontdoor_firewall_policy", "scaleway": "scaleway_edge_services_waf_stage"}


def make(cloud: str, balancer: bool = True, **kw):
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud=cloud, envs="staging-prod",
                                     shared_host=True), CATALOG)
    if balancer:
        p.add(LB[cloud], "infrastructure")
    p.add(CATALOG[cloud].services["cdn"], "infrastructure", **kw)
    return p


def result(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True)


def test_quatre_clouds_ont_un_cdn_ni_ovhcloud_ni_outscale():
    assert {c: CATALOG[c].services.get("cdn") for c in CLOUDS} == CLOUDS
    assert not CATALOG["ovhcloud"].services.get("cdn") and not CATALOG["outscale"].services.get("cdn")
    assert set(cdn.CDN) == set(CLOUDS.values())


@pytest.mark.parametrize("cloud", CLOUDS)
def test_cdn_et_pare_feu_devant_le_repartiteur(cloud):
    r = result(make(cloud))
    m = r.files["infra/terraform/main.tf"]
    assert CDN_RESOURCE[cloud] in m and WAF[cloud] in m
    assert any("pare-feu" in n for n in r.ir.notes)
    assert "cdn_" in r.files["infra/terraform/outputs.tf"]


def test_origine_repartiteur_sinon_machines_sinon_variable():
    assert "domain_name = aws_lb.production.dns_name" in result(make("aws")).files["infra/terraform/main.tf"]
    assert "aws_instance.production[0].public_dns" in result(make("aws", balancer=False)).files["infra/terraform/main.tf"]
    k = build_starter(StarterAnswers(forge="gitlab", hosting="kubernetes-managed", cloud="aws", envs="staging-prod"),
                      CATALOG)
    k.add("aws-cloudfront", "infrastructure")
    r = result(k)
    assert "domain_name = var.cdn_origin" in r.files["infra/terraform/main.tf"]
    assert 'variable "cdn_origin"' in r.files["infra/terraform/variables.tf"]
    assert any("cdn_origin" in n for n in r.ir.notes)
    given = result(make("aws", origin="origine.exemple.fr")).files["infra/terraform/main.tf"]
    assert 'domain_name = "origine.exemple.fr"' in given


def test_mise_en_cache_coupee_par_defaut_et_choisie_sur_demande():
    off = result(make("aws")).files["infra/terraform/main.tf"]
    on = result(make("aws", cache="standard")).files["infra/terraform/main.tf"]
    assert cdn.CACHING_DISABLED in off and cdn.CACHING_OPTIMIZED in on
    assert "USE_ORIGIN_HEADERS" in result(make("gcp")).files["infra/terraform/main.tf"]
    assert "CACHE_ALL_STATIC" in result(make("gcp", cache="standard")).files["infra/terraform/main.tf"]


def test_aws_pare_feu_en_us_east_1_et_limite_sur_cinq_minutes():
    f = result(make("aws", rate_limit=100)).files["infra/terraform/main.tf"]
    assert 'alias  = "us_east_1"' in f and "provider = aws.us_east_1" in f
    assert "limit              = 500" in f
    assert "us_east_1" not in result(make("gcp")).files["infra/terraform/main.tf"]


def test_gcp_certificat_gere_seulement_avec_un_domaine():
    assert "managed_ssl_certificate" not in result(make("gcp")).files["infra/terraform/main.tf"]
    assert "managed_ssl_certificate" in result(make("gcp", domain="exemple.fr")).files["infra/terraform/main.tf"]


def test_azure_regles_gerees_en_premium_seulement():
    assert "Microsoft_DefaultRuleSet" not in result(make("azure")).files["infra/terraform/main.tf"]
    assert "Microsoft_DefaultRuleSet" in result(make("azure", sku="Premium_AzureFrontDoor")).files["infra/terraform/main.tf"]


def test_scaleway_demande_un_repartiteur_et_n_ecrit_rien_sans():
    diag = {d.rule_id for d in ENGINE.evaluate(make("scaleway", balancer=False))}
    assert "R29" in diag
    r = result(make("scaleway", balancer=False))
    assert "scaleway_edge_services" not in r.files["infra/terraform/main.tf"]


def test_la_palette_ne_propose_que_le_cdn_du_cloud_du_projet():
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud="gcp", envs="prod"), CATALOG)
    keep, _ = adapted([CATALOG[t] for t in CLOUDS.values()], p, CATALOG)
    assert [t.id for t in keep] == ["gcp-cdn"]
