# SPDX-License-Identifier: Apache-2.0
"""1.1 : capacité « cache managé » — un cache clé-valeur par cloud, branché comme une base managée."""

from __future__ import annotations

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.compat import adapted
from devops_builder.databases import MANAGED_CACHES, databases
from devops_builder.generators import generate
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
CLOUDS = {"aws": "aws-elasticache", "gcp": "gcp-memorystore", "azure": "azure-redis", "scaleway": "scaleway-redis",
          "ovhcloud": "ovh-valkey"}
RESOURCE = {"aws": 'resource "aws_elasticache_replication_group" "cache_aws_',
            "gcp": 'resource "google_redis_instance" "cache_gcp_',
            "azure": 'resource "azurerm_redis_cache" "cache_azure_',
            "scaleway": 'resource "scaleway_redis_cluster" "cache_scaleway_',
            "ovhcloud": 'resource "ovh_cloud_project_database" "cache_ovh_'}


def make(cloud: str, *extra: str):
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud=cloud, envs="staging-prod",
                                     shared_host=True), CATALOG)
    p.add(CATALOG[cloud].services["cache"], "data")
    for t in extra:
        p.add(t, "infrastructure")
    return p


def files(p) -> dict[str, str]:
    return generate(p, CATALOG, ENGINE, allow_blocking=True).files


def test_cinq_clouds_ont_un_cache_outscale_non():
    assert {c: CATALOG[c].services.get("cache") for c in CLOUDS} == CLOUDS
    assert not CATALOG["outscale"].services.get("cache")
    assert set(MANAGED_CACHES) == set(CLOUDS.values())
    for tool_id in CLOUDS.values():
        assert "key-value" in CATALOG[tool_id].provides


@pytest.mark.parametrize("cloud", CLOUDS)
def test_une_instance_par_environnement_et_connexion_tls(cloud):
    p = make(cloud)
    db = databases(p, CATALOG)[0]
    assert db.mode == "managed" and db.engine.family == "key-value"
    assert db.url("h", "pw").startswith("rediss://:pw@h:")
    m = files(p)["infra/terraform/main.tf"]
    assert m.count(RESOURCE[cloud]) == 2                                # staging et production


def test_aws_reseau_du_projet_sinon_reseau_par_defaut_une_seule_fois():
    m = files(make("aws", "aws-vpc"))["infra/terraform/main.tf"]
    assert "subnet_ids = aws_subnet.private[*].id" in m and 'data "aws_vpc"' not in m
    m = files(make("aws", "aws-ec2", "aws-elb"))["infra/terraform/main.tf"]
    assert m.count('data "aws_vpc" "default"') == 1 and "data.aws_subnets.default.ids" in m


def test_secret_ecrit_dans_le_coffre_du_cloud():
    m = files(make("aws", "aws-secrets-manager"))["infra/terraform/main.tf"]
    assert "aws_elasticache_replication_group.cache_aws_production.primary_endpoint_address" in m
    assert 'rediss://:${random_password.cache_aws_production.result}@' in m
    m = files(make("azure", "azure-key-vault"))["infra/terraform/main.tf"]
    assert "urlencode(azurerm_redis_cache.cache_azure_production.primary_access_key)" in m


def test_pas_de_sauvegarde_annoncee_pour_un_cache():
    from devops_builder.datainfo import infos
    info = infos(make("gcp"), CATALOG)["gcp-memorystore"]
    assert "reconstructibles" in info.backup and info.badge == "Service managé"


def test_la_palette_ne_propose_que_le_cache_du_cloud_du_projet():
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud="gcp", envs="prod"), CATALOG)
    keep, _ = adapted([CATALOG[t] for t in CLOUDS.values()], p, CATALOG)
    assert [t.id for t in keep] == ["gcp-memorystore"]
