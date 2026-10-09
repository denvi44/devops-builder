"""Assistant de démarrage et suggestions : invariants sur toutes les combinaisons."""

from __future__ import annotations

import itertools

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.model import ENV_PRESETS, Project
from devops_builder.rules import RuleEngine
from devops_builder.starter import (
    FORGES,
    HOSTINGS,
    IAC,
    OBSERVABILITY,
    StarterAnswers,
    build_starter,
    clouds_for,
    validate,
)
from devops_builder.suggest import check_table, suggestions

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)


def all_answers():
    for forge, hosting, sec, envs, gitops, obs, iac, security in itertools.product(
            FORGES, HOSTINGS, [False, True], ENV_PRESETS, [False, True], OBSERVABILITY, IAC, [False, True]):
        for cloud in clouds_for(hosting, sec) or [None]:
            a = StarterAnswers(forge=forge, hosting=hosting, secnumcloud=sec, envs=envs, gitops=gitops,
                               observability=obs, iac=iac, cloud=cloud, security=security, quality=True)
            if not validate(a):
                yield a


def test_aucune_combinaison_de_l_assistant_n_est_bloquante():
    count = 0
    for a in all_answers():
        count += 1
        blocking = RuleEngine.blocking(ENGINE.evaluate(build_starter(a, CATALOG)))
        assert not blocking, (a, [d.message for d in blocking])
    assert count > 4000


@pytest.mark.parametrize("hosting", list(HOSTINGS))
def test_l_assistant_genere_pour_chaque_hebergement(hosting):
    for cloud in clouds_for(hosting, False) or [None]:
        a = StarterAnswers(hosting=hosting, cloud=cloud, envs="dev-staging-prod", gitops=True)
        result = generate(build_starter(a, CATALOG), CATALOG)
        assert any(k.endswith((".gitlab-ci.yml",)) for k in result.files)
        # OKS et Azure Container Apps : Terraform en commentaire seulement (limite connue)
        known = {"oks", "azure-container-apps"}
        assert [t.id for t in result.ir.unsupported if t.curated and t.id not in known] == []


def test_secnumcloud_restreint_les_clouds():
    assert set(clouds_for("kubernetes-managed", True)) == {"outscale", "ovhcloud"}
    assert clouds_for("serverless", True) == []
    assert validate(StarterAnswers(hosting="serverless", secnumcloud=True))


def test_ci_native_de_la_forge():
    p = build_starter(StarterAnswers(forge="github"), CATALOG)
    assert {"github", "github-actions", "ghcr", "dependabot"} <= p.tool_ids()
    p = build_starter(StarterAnswers(forge="gitlab"), CATALOG)
    assert "gitlab-ci" in p.tool_ids() and "harbor" not in p.tool_ids()  # registre intégré de GitLab


def test_table_de_suggestions_coherente():
    assert check_table(CATALOG) == []


def test_suggestions_filtrees():
    p = Project(target="docker-host")
    p.add("argo-cd", "deploy")
    assert suggestions(p, CATALOG, "argo-cd") == []  # Helm ou Kustomize exigent un cluster
    p.add("k3s", "infrastructure")
    assert [t.id for t in suggestions(p, CATALOG, "argo-cd")][:2] == ["helm", "kustomize"]
    p.add("helm", "deploy")
    assert "helm" not in [t.id for t in suggestions(p, CATALOG, "argo-cd")]
    q = Project(license_policy="oss-only")
    q.add("prometheus", "observability")
    assert all(t.is_oss for t in suggestions(q, CATALOG, "prometheus"))
