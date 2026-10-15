# SPDX-License-Identifier: Apache-2.0
"""Renovate : application GitHub, job planifié GitLab CI, workflow Gitea Actions, note ailleurs."""

from __future__ import annotations

import yaml
from test_rules import CATALOG

from devops_builder.generators import render
from devops_builder.generators.extras import RENOVATE_IMAGE
from devops_builder.starter import StarterAnswers, build_starter


def _files(forge, ci=None):
    p = build_starter(StarterAnswers(forge=forge, ci=ci, hosting="docker-host", envs="staging-prod"), CATALOG)
    assert p.bricks_for("renovate") or forge == "github"
    if not p.bricks_for("renovate"):
        p.add("renovate", CATALOG["renovate"].stage)
    return render(p, CATALOG)


def test_gitlab_job_planifie_seul_dans_son_pipeline():
    files, ir = _files("gitlab")
    doc = yaml.safe_load(files[".gitlab-ci.yml"])
    job = doc["renovate"]
    assert job["image"]["name"] == RENOVATE_IMAGE and job["script"] == ["renovate"]
    assert job["rules"] == [{"if": '$CI_PIPELINE_SOURCE == "schedule" && $RENOVATE == "1"'}]
    assert doc["stages"][-1] == "renovate"
    others = [k for k, v in doc.items() if isinstance(v, dict) and "script" in v and k != "renovate"]
    assert others
    for name in others:   # aucun build ni déploiement dans le pipeline de Renovate
        assert doc[name]["rules"][0] == {"if": '$RENOVATE == "1"', "when": "never"}, name
        assert len(doc[name]["rules"]) >= 2, name
    guide = files["docs/mise-en-route.md"]
    assert "pipeline_schedules" in guide and "-d key=RENOVATE -d value=1" in guide


def test_gitea_workflow_planifie():
    files, _ = _files("gitea", "gitea-actions")
    wf = yaml.safe_load(files[".gitea/workflows/renovate.yml"])
    job = wf["jobs"]["renovate"]
    assert job["container"] == RENOVATE_IMAGE and job["env"]["RENOVATE_PLATFORM"] == "gitea"
    assert wf["on"]["schedule"][0]["cron"] == "0 4 * * 1-5"


def test_github_par_l_application_et_autres_ci_par_une_note():
    files, ir = _files("github")
    assert "renovate" not in files.get(".github/workflows/pipeline.yml", "").split("jobs:")[-1].split("\n  ")[0]
    assert any("application GitHub Renovate" in n for n in ir.notes)
    files, ir = _files("gitlab", "jenkins")
    assert not any(k.endswith("renovate.yml") for k in files)
    assert any(RENOVATE_IMAGE in n for n in ir.notes)
