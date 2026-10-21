# SPDX-License-Identifier: Apache-2.0
"""1.1 : capacité « fonctions serverless » — une fonction par environnement, déclencheur HTTP, déploiement par la CI."""

from __future__ import annotations

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.compat import adapted
from devops_builder.generators import functions, generate
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
CLOUDS = {"aws": "aws-lambda", "gcp": "gcp-functions", "azure": "azure-functions", "scaleway": "scaleway-functions"}
RESOURCE = {"aws": 'resource "aws_lambda_function" "fn_', "gcp": 'resource "google_cloudfunctions2_function" "fn_',
            "azure": 'resource "azurerm_linux_function_app" "fn_', "scaleway": 'resource "scaleway_function" "fn_'}


def make(cloud: str, **kw):
    p = build_starter(StarterAnswers(forge="gitlab", hosting="vm" if cloud == "scaleway" else "serverless", cloud=cloud,
                                     envs="staging-prod", shared_host=cloud == "scaleway"), CATALOG)
    for uid in [b.uid for _, b in p.all_bricks() if b.tool in ("ecs-fargate", "cloud-run", "azure-container-apps")]:
        p.remove(uid)       # les fonctions remplacent le déploiement de conteneurs
    p.add(CATALOG[cloud].services["functions"], "deploy", **kw)
    return p


def result(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True)


def deploy_steps(r):
    return [s for s in r.ir.steps if s.id.startswith("deploy")]


def test_quatre_clouds_ont_des_fonctions_ni_ovhcloud_ni_outscale():
    assert {c: CATALOG[c].services.get("functions") for c in CLOUDS} == CLOUDS
    assert not CATALOG["ovhcloud"].services.get("functions") and not CATALOG["outscale"].services.get("functions")
    assert set(functions.FUNCTIONS) == set(CLOUDS.values())


@pytest.mark.parametrize("cloud", CLOUDS)
def test_une_fonction_par_environnement_et_adresse_en_sortie(cloud):
    r = result(make(cloud))
    m, o = r.files["infra/terraform/main.tf"], r.files["infra/terraform/outputs.tf"]
    assert m.count(RESOURCE[cloud]) == 2 and "fn_staging" in m and "fn_production" in m
    assert 'output "fn_staging_url"' in o and 'output "fn_production_url"' in o


def test_le_code_est_deploye_par_la_ci_et_non_reecrit_par_la_pile():
    for cloud, needle in (("aws", "aws lambda update-function-code"), ("gcp", "gcloud functions deploy"),
                          ("azure", "az functionapp deployment source config-zip")):
        r = result(make(cloud))
        steps = deploy_steps(r)
        assert steps and any(needle in line for line in steps[0].script), cloud
    assert "ignore_changes" in result(make("aws")).files["infra/terraform/main.tf"]
    assert "ignore_changes" in result(make("gcp")).files["infra/terraform/main.tf"]


def test_scaleway_sans_etape_de_deploiement_et_avec_une_note():
    r = result(make("scaleway"))
    assert not any(s.tool == "scaleway-functions" for s in r.ir.steps)
    assert any("scw" in n for n in r.ir.notes)


def test_fournisseur_archive_seulement_pour_le_code_de_remplacement():
    assert "hashicorp/archive" in result(make("aws")).files["infra/terraform/versions.tf"]
    assert "hashicorp/archive" in result(make("gcp")).files["infra/terraform/versions.tf"]
    assert "hashicorp/archive" not in result(make("azure")).files["infra/terraform/versions.tf"]
    assert "function-placeholder.zip" in result(make("aws")).files["infra/terraform/.gitignore"]


def test_nom_de_la_production_et_runtime_node():
    m = result(make("aws", function="api", runtime="nodejs22.x", handler="index.handler")).files["infra/terraform/main.tf"]
    assert 'function_name    = "api"' in m and 'function_name    = "api-staging"' in m
    assert 'filename = "index.js"' in m and "exports.handler" in m


def test_runtime_sans_code_de_remplacement_signale():
    r = result(make("aws", runtime="java21", handler="fr.Main::handle"))
    assert any("Python et Node.js" in n for n in r.ir.notes)


def test_la_palette_ne_propose_que_les_fonctions_du_cloud_du_projet():
    p = build_starter(StarterAnswers(forge="gitlab", hosting="serverless", cloud="gcp", envs="prod"), CATALOG)
    keep, _ = adapted([CATALOG[t] for t in CLOUDS.values()], p, CATALOG)
    assert [t.id for t in keep] == ["gcp-functions"]
