# SPDX-License-Identifier: Apache-2.0
"""1.1 : capacité « file de messages » — une file par environnement, adresse en sortie de la pile."""

from __future__ import annotations

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.compat import adapted
from devops_builder.generators import generate, queue
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
CLOUDS = {"aws": "aws-sqs", "gcp": "gcp-pubsub", "azure": "azure-service-bus", "scaleway": "scaleway-queues",
          "ovhcloud": "ovh-kafka"}
RESOURCE = {"aws": 'resource "aws_sqs_queue" "queue_', "gcp": 'resource "google_pubsub_topic" "queue_',
            "azure": 'resource "azurerm_servicebus_queue" "queue_', "scaleway": 'resource "scaleway_mnq_sqs_queue" "queue_',
            "ovhcloud": 'resource "ovh_cloud_project_database_kafka_topic" "queue_'}


def make(cloud: str, **kw):
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud=cloud, envs="staging-prod",
                                     shared_host=True), CATALOG)
    p.add(CATALOG[cloud].services["message-queue"], "infrastructure", **kw)
    return p


def result(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True)


def test_cinq_clouds_ont_une_file_outscale_non():
    assert {c: CATALOG[c].services.get("message-queue") for c in CLOUDS} == CLOUDS
    assert not CATALOG["outscale"].services.get("message-queue")
    assert set(queue.QUEUE) == set(CLOUDS.values())
    for tool_id, cloud in queue.QUEUE.items():
        assert CATALOG[tool_id].provider == cloud and "message-queue" in CATALOG[tool_id].provides


@pytest.mark.parametrize("cloud", CLOUDS)
def test_une_file_par_environnement_et_adresse_en_sortie(cloud):
    r = result(make(cloud))
    m, o = r.files["infra/terraform/main.tf"], r.files["infra/terraform/outputs.tf"]
    assert m.count(RESOURCE[cloud]) == (4 if cloud == "aws" else 2) and "_staging" in m and "_production" in m
    assert 'output "queue_staging_url"' in o and 'output "queue_production_url"' in o
    assert any("QUEUE_URL" in n for n in r.ir.notes)


def test_la_production_porte_le_nom_choisi_les_autres_un_suffixe():
    m = (
        result(make("aws", queue="commandes")).files["infra/terraform/main.tf"])
    assert 'name                      = "commandes"' in m and 'name                      = "commandes-staging"' in m


def test_conservation_bornee_de_un_a_sept_jours():
    m = result(make("aws", retention_days=30)).files["infra/terraform/main.tf"]
    assert "message_retention_seconds = 604800" in m


def test_sqs_a_sa_file_de_messages_morts_et_scaleway_sort_une_cle_sensible():
    m = result(make("aws")).files["infra/terraform/main.tf"]
    assert m.count("deadLetterTargetArn") == 2
    sw = result(make("scaleway")).files["infra/terraform/outputs.tf"]
    assert "queue_production_secret_key" in sw and sw.count("sensitive   = true") == 4 and "sensitive" in sw


def test_la_palette_ne_propose_que_la_file_du_cloud_du_projet():
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm", cloud="gcp", envs="prod"), CATALOG)
    keep, _ = adapted([CATALOG[t] for t in CLOUDS.values()], p, CATALOG)
    assert [t.id for t in keep] == ["gcp-pubsub"]
