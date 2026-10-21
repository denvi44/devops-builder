# SPDX-License-Identifier: Apache-2.0
"""1.1 : capacité « chiffrement (KMS) » — une clé par cloud, utilisée par les ressources AWS du projet."""

from __future__ import annotations

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.compat import adapted
from devops_builder.generators import generate, kms
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
CLOUDS = {"aws": "aws-kms", "gcp": "gcp-kms", "azure": "azure-kms", "scaleway": "scaleway-key-manager"}
KEY = {"aws": 'resource "aws_kms_key" "main"', "gcp": 'resource "google_kms_crypto_key" "main"',
       "azure": 'resource "azurerm_key_vault_key" "main"', "scaleway": 'resource "scaleway_key_manager_key" "main"'}


def make(cloud: str, *extra: str, **kw):
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud=cloud, envs="staging-prod",
                                     shared_host=True), CATALOG)
    p.add(CATALOG[cloud].services["kms"], "infrastructure", **kw)
    for t in extra:
        p.add(t, "data" if t in ("aws-elasticache", "aws-rds") else "infrastructure")
    return p


def files(p) -> dict[str, str]:
    return generate(p, CATALOG, ENGINE, allow_blocking=True).files


def test_quatre_clouds_ont_un_kms_ni_ovhcloud_ni_outscale():
    assert {c: CATALOG[c].services.get("kms") for c in CLOUDS} == CLOUDS
    assert not CATALOG["ovhcloud"].services.get("kms") and not CATALOG["outscale"].services.get("kms")
    assert set(kms.KMS) == set(CLOUDS.values())


@pytest.mark.parametrize("cloud", CLOUDS)
def test_la_cle_est_creee_avec_rotation_et_donnee_en_sortie(cloud):
    f = files(make(cloud))
    assert KEY[cloud] in f["infra/terraform/main.tf"]
    assert "kms_key" in f["infra/terraform/outputs.tf"]
    assert any(w in f["infra/terraform/main.tf"] for w in ("enable_key_rotation", "rotation_period", "rotation_policy"))


def test_aws_la_cle_chiffre_disques_files_cache_et_secrets():
    m = files(make("aws", "aws-ec2", "aws-sqs", "aws-elasticache", "aws-secrets-manager"))["infra/terraform/main.tf"]
    assert "kms_key_id  = aws_kms_key.main.arn" in m                      # disque racine
    assert m.count("kms_master_key_id         = aws_kms_key.main.arn") == 4   # SQS et sa file des messages morts, par environnement
    assert "sqs_managed_sse_enabled" not in m
    assert "kms_key_id                 = aws_kms_key.main.arn" in m           # ElastiCache
    assert 'resource "aws_secretsmanager_secret"' in m and "kms_key_id" in m.split("aws_secretsmanager_secret")[1]


def test_aws_sans_kms_rien_ne_change_pour_les_ressources():
    m = files(make("aws", "aws-ec2"))["infra/terraform/main.tf"]
    assert "aws_kms_key" in m
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud="aws", envs="staging-prod",
                                     shared_host=True), CATALOG)
    p.add("aws-sqs", "infrastructure")
    base = files(p)["infra/terraform/main.tf"]
    assert "kms" not in base and "sqs_managed_sse_enabled" in base


def test_azure_un_seul_client_config_avec_ou_sans_coffre_de_secrets():
    m = files(make("azure", "azure-key-vault"))["infra/terraform/main.tf"]
    assert m.count('data "azurerm_client_config" "current"') == 1
    assert files(make("azure"))["infra/terraform/main.tf"].count('data "azurerm_client_config" "current"') == 1


def test_les_autres_clouds_disent_que_le_rattachement_reste_a_faire():
    from devops_builder.generators import generate as g
    r = g(make("gcp"), CATALOG, ENGINE, allow_blocking=True)
    assert any("reste à faire" in n for n in r.ir.notes)


def test_la_palette_ne_propose_que_le_kms_du_cloud_du_projet():
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud="gcp", envs="prod"), CATALOG)
    keep, _ = adapted([CATALOG[t] for t in CLOUDS.values()], p, CATALOG)
    assert [t.id for t in keep] == ["gcp-kms"]
