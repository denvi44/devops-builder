"""L'application d'abord : analyse du dossier, projet pré-rempli, catalogue restreint au projet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devops_builder import appscan
from devops_builder.catalog import default_catalog
from devops_builder.cli import main as cli
from devops_builder.compat import adapted, incompatibility
from devops_builder.generators import generate
from devops_builder.model import Project
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, answers_from_profile, build_starter

CATALOG = default_catalog()


def tree(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content, encoding="utf-8")
    return root


GIT_CONFIG = '[core]\n\tbare = false\n[remote "origin"]\n\turl = {url}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n'


@pytest.fixture
def fastapi(tmp_path):
    return tree(tmp_path / "Commandes API", {
        "pyproject.toml": '[project]\nname = "commandes-api"\ndependencies = ["fastapi", "uvicorn"]\n',
        "tests/test_api.py": "def test_ok():\n    assert True\n",
        "Dockerfile": "FROM python:3.12-slim AS build\nFROM python:3.12-slim\nEXPOSE 8081\nCMD [\"uvicorn\"]\n",
        "charts/commandes/Chart.yaml": "apiVersion: v2\nname: commandes\nversion: 0.1.0\n",
        ".git/config": GIT_CONFIG.format(url="git@gitlab.example.fr:equipe/commandes.git"),
        ".gitlab-ci.yml": "stages: [test]\n",
        "renovate.json": "{}",
        "node_modules/ignore/package.json": '{"name": "pas-moi"}',
    })


# ------------------------------------------------------------------ analyse
def test_analyse_python_fastapi(fastapi):
    p = appscan.scan(fastapi)
    assert (p.language, p.framework, p.name, p.image_name) == ("python", "fastapi", "commandes-api", "commandes-api")
    assert p.port == 8081 and "EXPOSE" in p.port_source
    assert p.dockerfile and p.base_image == "python:3.12-slim"
    assert p.helm and p.hosting_hint == "kubernetes"
    assert (p.forge, p.ci, p.dependencies) == ("gitlab", "gitlab-ci", "renovate")
    assert p.has_tests and any(line.startswith("Chart Helm") for line in p.summary())


@pytest.mark.parametrize("files,expected", [
    ({"package.json": json.dumps({"name": "@izinum/portail", "dependencies": {"next": "15"},
                                  "scripts": {"test": "vitest"}})}, ("node", "next", 3000, "portail")),
    ({"pom.xml": "<project><artifactId>facturation</artifactId><parent>spring-boot</parent></project>"},
     ("java", "spring-boot", 8080, "facturation")),
    ({"go.mod": "module github.com/izinum/relais\nrequire github.com/gin-gonic/gin v1.10.0\n", "main_test.go": ""},
     ("go", "gin", 8080, "relais")),
    ({"src/Api/Api.csproj": '<Project Sdk="Microsoft.NET.Sdk.Web"></Project>'}, ("dotnet", "aspnet", 8080, "Api")),
    ({"requirements.txt": "flask\n"}, ("python", "flask", 5000, None)),
    ({"index.html": "<h1>site</h1>"}, ("other", "", None, None)),
])
def test_analyse_des_langages(tmp_path, files, expected):
    p = appscan.scan(tree(tmp_path / "app", files))
    language, framework, port, name = expected
    assert (p.language, p.framework, p.port) == (language, framework, port)
    if name:
        assert p.name == name
    assert not p.dockerfile and "Buildpacks" in " ".join(p.summary())


def test_forges_et_ci(tmp_path):
    cases = {"https://github.com/izinum/a.git": "github", "git@bitbucket.org:i/a.git": "bitbucket",
             "https://izinum@dev.azure.com/izinum/p/_git/a": "azure-repos", "https://codeberg.org/i/a": "gitea",
             "ssh://git@gitea.izinum.fr:2222/i/a.git": "gitea", "https://git.interne.fr/i/a.git": None}
    for url, forge in cases.items():
        root = tree(tmp_path / str(abs(hash(url))), {".git/config": GIT_CONFIG.format(url=url)})
        assert appscan.scan(root).forge == forge, url
    root = tree(tmp_path / "gh", {".github/workflows/ci.yml": "on: push\n"})
    p = appscan.scan(root)
    assert p.ci == "github-actions" and p.forge == "github"


def test_iac_et_deploiement(tmp_path):
    p = appscan.scan(tree(tmp_path / "a", {"infra/main.tf": "", "infra/.terraform.lock.hcl": 'provider "registry.opentofu.org/hashicorp/aws"',
                                           "deploy/kustomization.yaml": "resources: []", "compose.yaml": "services: {}"}))
    assert p.iac == "opentofu" and p.kustomize and p.compose and p.hosting_hint == "kubernetes"
    assert appscan.scan(tree(tmp_path / "b", {"main.tf": ""})).iac == "terraform"


def test_dossier_absent(tmp_path):
    with pytest.raises(ValueError):
        appscan.scan(tmp_path / "nulle-part")


# ------------------------------------------------------------------ projet depuis l'application
def test_projet_construit_depuis_l_analyse(fastapi):
    a, taken = answers_from_profile(appscan.scan(fastapi), CATALOG)
    assert (a.forge, a.hosting, a.port, a.image_name, a.dependency_tool) == ("gitlab", "kubernetes", 8081, "commandes-api", "renovate")
    p = build_starter(a, CATALOG)
    assert p.app.source == str(fastapi.resolve()) and p.app.port == 8081
    assert {"gitlab", "gitlab-ci", "buildkit", "helm", "k3s", "renovate"} <= p.tool_ids()
    assert RuleEngine.blocking(RuleEngine(CATALOG).evaluate(p)) == []
    generate(p, CATALOG)
    assert Project.from_yaml(p.to_yaml()).app.source == str(fastapi.resolve())
    assert "  source: ''" not in Project().to_yaml()


def test_sans_dockerfile_buildpacks(tmp_path):
    root = tree(tmp_path / "site", {"package.json": '{"name": "site"}', ".git/config": GIT_CONFIG.format(url="https://github.com/i/site")})
    p = build_starter(answers_from_profile(appscan.scan(root), CATALOG)[0], CATALOG)
    assert "buildpacks" in p.tool_ids() and "buildkit" not in p.tool_ids() and "github-actions" in p.tool_ids()
    assert RuleEngine.blocking(RuleEngine(CATALOG).evaluate(p)) == []


def test_ci_existante_reprise_si_compatible(tmp_path):
    root = tree(tmp_path / "a", {"requirements.txt": "", "Jenkinsfile": "pipeline {}",
                                 ".git/config": GIT_CONFIG.format(url="git@gitlab.com:i/a.git")})
    a, taken = answers_from_profile(appscan.scan(root), CATALOG)
    assert a.ci == "jenkins" and any("Jenkins" in t for t in taken)
    root = tree(tmp_path / "b", {"requirements.txt": "", "azure-pipelines.yml": "",
                                 ".git/config": GIT_CONFIG.format(url="git@gitlab.com:i/b.git")})
    assert answers_from_profile(appscan.scan(root), CATALOG)[0].ci is None      # Azure Pipelines ne lit pas GitLab


def test_briques_proposees_pour_un_projet_existant(fastapi):
    p = Project(name="t", target="kubernetes")
    p.add("gitlab", "source")
    proposals = dict(appscan.proposed_bricks(appscan.scan(fastapi), p, CATALOG))
    assert {"gitlab-ci", "buildkit", "unit-tests", "helm", "renovate"} <= set(proposals)
    assert "gitlab" not in proposals and "docker-compose" not in proposals


def test_cli_scan_et_init(fastapi, tmp_path, capsys):
    assert cli(["scan", str(fastapi)]) == 0
    assert "Chart Helm" in capsys.readouterr().out
    assert cli(["scan", str(fastapi), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["port"] == 8081
    out = tmp_path / "commandes.devops.yaml"
    assert cli(["init", str(fastapi), "-o", str(out), "--envs", "dev-recette-prod"]) == 0
    p = Project.load(out)
    assert [e.id for e in p.environments] == ["dev", "recette", "production"] and p.app.port == 8081
    assert cli(["init", str(fastapi), "-o", str(out), "--hosting", "serverless"]) == 1   # cloud manquant


# ------------------------------------------------------------------ catalogue restreint
def _project(target: str, *tools: str, **kw) -> Project:
    p = Project(name="t", target=target, **kw)
    for t in tools:
        p.add(t, CATALOG[t].stage)
    return p


def test_raisons_d_ecarter_une_brique():
    p = _project("docker-host", "gitlab", "gitlab-ci", "aws")
    why = lambda tid: incompatibility(CATALOG[tid], p, CATALOG)  # noqa: E731
    assert "Kubernetes" in why("argo-cd")
    assert "GitLab" in why("github-actions")
    assert "orchestrateur CI déjà choisi : GitLab CI" == why("jenkins")
    assert why("gke") == "service Google Cloud, alors que le projet utilise Amazon Web Services"
    assert why("gitlab-ci") == "déjà dans le pipeline"
    assert why("trivy") is None and why("ecr") is None
    oss = _project("kubernetes", license_policy="oss-only")
    assert "open source" in incompatibility(CATALOG["terraform"], oss, CATALOG)
    sec = _project("kubernetes-managed", secnumcloud=True)
    assert "SecNumCloud" in incompatibility(CATALOG["eks"], sec, CATALOG)
    k8s = _project("kubernetes", "flux")
    assert "GitOps déjà choisi" in incompatibility(CATALOG["argo-cd"], k8s, CATALOG)
    tf = _project("kubernetes", "opentofu")
    assert "OpenTofu" in incompatibility(CATALOG["terraform"], tf, CATALOG)
    assert "inadapté" in incompatibility(CATALOG["docker-compose"], _project("kubernetes"), CATALOG)


def test_projet_vide_sur_hote_docker():
    tools, reasons = adapted(CATALOG.curated(), Project(name="t", target="docker-host"), CATALOG)
    assert reasons and all(CATALOG[t].kubernetes_only for t, why in reasons.items() if "Kubernetes" in why)
    assert "docker-compose" in {t.id for t in tools}


def test_aucune_brique_ajoutee_par_l_assistant_n_est_ecartee():
    """Les choix par défaut restent cohérents avec ce que l'assistant construit lui-même."""
    from devops_builder.starter import FORGES, HOSTINGS, clouds_for
    for forge in FORGES:
        for hosting in HOSTINGS:
            for cloud in clouds_for(hosting, False) or [None]:
                p = build_starter(StarterAnswers(forge=forge, hosting=hosting, cloud=cloud), CATALOG)
                for _, b in p.all_bricks():
                    others = p.model_copy(deep=True)
                    others.remove(b.uid)
                    assert incompatibility(CATALOG[b.tool], others, CATALOG) is None, (forge, hosting, cloud, b.tool,
                        incompatibility(CATALOG[b.tool], others, CATALOG))
