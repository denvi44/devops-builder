"""Génération : les 3 pipelines de référence et une matrice CI × déploiement.

Chaque fichier YAML produit doit se charger ; quand les outils sont installés,
les sorties sont aussi validées contre les schémas officiels (check-jsonschema)
et par actionlint pour GitHub Actions.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from devops_builder.catalog import default_catalog
from devops_builder.generators import BlockingDiagnostics, generate
from devops_builder.model import Project
from devops_builder.rules import RuleEngine

CATALOG = default_catalog()
EXAMPLES = sorted((Path(__file__).parents[1] / "devops_builder" / "data" / "examples").glob("*.yaml"))

SCHEMAS = {
    ".gitlab-ci.yml": "vendor.gitlab-ci",
    ".github/workflows/pipeline.yml": "vendor.github-workflows",
    "azure-pipelines.yml": "vendor.azure-pipelines",
    "cloudbuild.yaml": "vendor.cloudbuild",
    ".woodpecker.yml": "vendor.woodpecker-ci",
    "deploy/docker-compose.yml": "vendor.compose-spec",
}


def project(target: str, *tools: str, **settings) -> Project:
    p = Project(name="matrice", target=target, environment="production")
    for k, v in settings.items():
        setattr(p, k, v)
    for t in tools:
        p.add(t, CATALOG[t].stage)
    return p


MATRIX = {
    "gitlab-compose": project("docker-host", "gitlab", "gitlab-ci", "buildkit", "unit-tests", "trivy",
                              "docker-compose", "traefik", "prometheus"),
    "github-helm-eks": project("kubernetes-managed", "github", "github-actions", "buildkit", "unit-tests",
                               "trivy", "cosign", "aws", "ecr", "eks", "opentofu", "s3", "helm"),
    "gitea-ansible": project("vm", "gitea", "gitea-actions", "buildah", "unit-tests", "zot", "ansible",
                             "docker-compose"),
    "jenkins-kustomize": project("kubernetes", "gitlab", "jenkins", "buildkit", "unit-tests", "harbor",
                                 "k3s", "kustomize", "sonarqube"),
    "woodpecker-flux": project("kubernetes", "gitea", "woodpecker", "buildah", "unit-tests", "zot", "k3s",
                               "flux", "kustomize"),
    "tekton-argo": project("kubernetes", "github", "tekton", "buildah", "unit-tests", "harbor", "rke2",
                           "argo-cd", "helm"),
    "azure-aks": project("kubernetes-managed", "azure-repos", "azure-pipelines", "buildkit", "unit-tests",
                         "azure", "acr", "aks", "terraform", "azure-blob", "helm", "azure-key-vault"),
    "codebuild-ecs": project("docker-host", "codecommit", "aws-codebuild", "buildkit", "unit-tests", "aws",
                             "ecr", "ecs-fargate", "grype", "syft"),
    "cloudbuild-run": project("docker-host", "github", "google-cloud-build", "buildpacks", "unit-tests",
                              "gcp", "artifact-registry", "cloud-run", "gcs", "opentofu"),
    "github-static-gke": project("kubernetes-managed", "github", "github-actions", "kaniko", "unit-tests",
                                 "gcp", "artifact-registry", "gke", "kustomize", cloud_auth="static"),
    "gitlab-scaleway": project("kubernetes-managed", "gitlab", "gitlab-ci", "buildkit", "scaleway",
                               "scaleway-registry", "kapsule", "opentofu", "helm"),
}


def _check_yaml(files: dict[str, str]) -> None:
    for rel, content in files.items():
        if rel.endswith((".yml", ".yaml")) and "/templates/" not in rel:
            list(yaml.safe_load_all(content))


def _validate_with_tools(tmp: Path, files: dict[str, str]) -> None:
    for rel, schema in SCHEMAS.items():
        if rel in files and shutil.which("check-jsonschema"):
            r = subprocess.run(["check-jsonschema", "--regex-variant", "python", "--builtin-schema", schema, str(tmp / rel)],
                               capture_output=True, text=True)
            assert r.returncode == 0, f"{rel} invalide ({schema}) :\n{r.stdout}{r.stderr}"
    wf = ".github/workflows/pipeline.yml"
    if wf in files and shutil.which("actionlint"):
        r = subprocess.run(["actionlint", "-shellcheck=", str(tmp / wf)], capture_output=True, text=True)
        assert r.returncode == 0, f"actionlint :\n{r.stdout}{r.stderr}"


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.stem for p in EXAMPLES])
def test_exemples_de_reference(path: Path, tmp_path: Path):
    result = generate(Project.load(path), CATALOG)
    assert "PIPELINE.md" in result.files
    _check_yaml(result.files)
    result.write(tmp_path)
    _validate_with_tools(tmp_path, result.files)


@pytest.mark.parametrize("name", list(MATRIX), ids=list(MATRIX))
def test_matrice(name: str, tmp_path: Path):
    p = MATRIX[name]
    blocking = RuleEngine.blocking(RuleEngine(CATALOG).evaluate(p))
    assert blocking == [], [d.message for d in blocking]
    result = generate(p, CATALOG)
    ci = result.ir.ci
    assert ci is not None
    assert len(result.files) >= 3
    _check_yaml(result.files)
    result.write(tmp_path)
    _validate_with_tools(tmp_path, result.files)


def test_generation_refusee_si_bloquant():
    p = project("docker-host", "argo-cd")
    with pytest.raises(BlockingDiagnostics):
        generate(p, CATALOG)


def test_aucun_secret_en_clair():
    for p in MATRIX.values():
        result = generate(p, CATALOG)
        for rel, content in result.files.items():
            assert "BEGIN PRIVATE KEY" not in content
            assert "AKIA" not in content, rel


def test_projet_aller_retour_yaml():
    p = MATRIX["github-helm-eks"]
    again = Project.from_yaml(p.to_yaml())
    assert again.model_dump() == p.model_dump()


def test_zip(tmp_path: Path):
    result = generate(MATRIX["gitlab-compose"], CATALOG)
    data = result.zip_bytes()
    assert data[:2] == b"PK"
