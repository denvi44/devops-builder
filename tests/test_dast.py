# SPDX-License-Identifier: Apache-2.0
"""ZAP : job d'analyse dynamique après le déploiement de l'environnement analysé."""

from __future__ import annotations

import subprocess

import pytest
import yaml
from test_data import CATALOG

from devops_builder.generators import dast, render
from devops_builder.ir import build_ir
from devops_builder.starter import StarterAnswers, build_starter


@pytest.fixture
def catalog():
    return CATALOG


def _project(catalog, envs="staging-prod", forge="gitlab", ci=None, hosting="docker-host", **zap):
    p = build_starter(StarterAnswers(forge=forge, ci=ci, hosting=hosting, envs=envs), catalog)
    p.add("zap", "security", **zap)
    return p


def test_job_apres_la_preproduction_et_avant_la_production(catalog):
    ir = build_ir(_project(catalog), catalog)
    ids = [s.id for s in ir.steps]
    assert ids.index("deploy-staging") + 1 == ids.index("dast-staging")
    step = ir.steps[ids.index("dast-staging")]
    assert step.needs == ["deploy-staging"] and step.allow_failure and step.main_only
    assert step.image == "ghcr.io/zaproxy/zaproxy:" + dast.DEFAULT_VERSION
    assert "dast-staging" in ir.steps[ids.index("deploy-production")].needs


def test_environnement_analyse_et_adresse_par_environnement(catalog):
    p = _project(catalog, envs="dev-staging-prod", environment="dev", blocking=True, scan="full")
    next(e for e in p.environments if e.id == "dev").overrides["zap"] = {"target_url": "https://dev.boutique.fr"}
    ir = build_ir(p, catalog)
    step = next(s for s in ir.steps if s.tool == "zap")
    assert step.id == "dast-dev" and step.needs == ["deploy-dev"] and not step.allow_failure
    assert any("zap-full-scan.py" in line for line in step.script)
    assert next(v for v in ir.variables if v.name == "ZAP_TARGET_URL").value == "https://dev.boutique.fr"


def test_un_seul_environnement(catalog):
    ir = build_ir(_project(catalog, envs="prod"), catalog)
    step = next(s for s in ir.steps if s.tool == "zap")
    assert step.id == "dast" and step.needs == ["deploy"]


def test_rules_tsv_lisible_par_zap(catalog):
    files, _ = render(_project(catalog), catalog)
    text = files[dast.RULES_FILE]
    # même lecture que load_config() de zap_common.py : 3 champs séparés par des tabulations
    rules = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        assert line.count("\t") >= 2, line
        key, action, _ = line.rstrip().split("\t", 2)
        assert key.isdigit() and action in ("IGNORE", "INFO", "WARN", "FAIL", "OUTOFSCOPE")
        rules[key] = action
    assert set(rules) == {rid for rid, _ in dast.FAIL_RULES}


def test_script_du_job(catalog):
    ir = build_ir(_project(catalog, scan="api", target_url="https://api.boutique.fr/openapi.json"), catalog)
    script = "\n".join(next(s for s in ir.steps if s.tool == "zap").script)
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0
    assert "zap-api-scan.py" in script and "-f openapi" in script and "-I" in script
    assert "/zap/wrk/zap-report.json" in script and 'exit "$code"' in script


def test_gitlab_ci(catalog):
    files, _ = render(_project(catalog), catalog)
    doc = yaml.safe_load(files[".gitlab-ci.yml"])
    stages = doc["stages"]
    assert stages.index("deploy-staging") < stages.index("dast") < stages.index("deploy-production")
    job = doc["dast-staging"]
    assert job["allow_failure"] is True and job["artifacts"]["when"] == "always"
    assert doc["variables"]["ZAP_TARGET_URL"].startswith("https://")


def test_github_actions_conteneur_en_root_et_rapport_toujours_publie(catalog):
    files, _ = render(_project(catalog, forge="github", hosting="kubernetes"), catalog)
    job = yaml.safe_load(files[".github/workflows/pipeline.yml"])["jobs"]["dast-staging"]
    assert job["container"] == {"image": "ghcr.io/zaproxy/zaproxy:" + dast.DEFAULT_VERSION, "options": "--user root"}
    assert job["continue-on-error"] is True
    upload = next(s for s in job["steps"] if "upload-artifact" in s.get("uses", ""))
    assert upload["if"] == "always()"


def test_ci_sans_echec_tolere_natif(catalog):
    for ci_id, check in (("tekton", "onError: continue"), ("google-cloud-build", "allowFailure: true"),
                         ("aws-codebuild", "Étape non bloquante en échec")):
        cloud = {"google-cloud-build": "gcp", "aws-codebuild": "aws"}.get(ci_id)
        p = build_starter(StarterAnswers(forge="github", ci=ci_id, hosting="kubernetes-managed" if cloud else
                                         "kubernetes", cloud=cloud, envs="staging-prod"), catalog)
        p.add("zap", "security")
        files, _ = render(p, catalog)
        assert any(check in content for content in files.values()), ci_id


def test_notes(catalog):
    _, ir = render(_project(catalog, envs="prod", scan="full"), catalog)
    text = " ".join(ir.notes)
    assert "ZAP_TARGET_URL" in text and "adresse d'exemple" in text and "scan complet attaque" in text
