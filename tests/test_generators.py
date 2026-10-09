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
    "renovate.json": "vendor.renovate",
    ".github/dependabot.yml": "vendor.dependabot",
}


def project(target: str, *tools: str, environment: str = "production", envs: str | None = None,
            **settings) -> Project:
    from devops_builder.model import env_preset
    p = Project(name="matrice", target=target, environment=environment)
    if envs:
        p.environments = env_preset(envs)
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
    "k3s-cilium-renovate": project("kubernetes", "gitlab", "gitlab-ci", "buildkit", "k3s", "cilium", "traefik",
                                   "helm", "renovate", "prometheus"),
    "rke2-cilium": project("kubernetes", "gitea", "woodpecker", "buildah", "zot", "rke2", "cilium", "helm"),
    "kubeadm-calico": project("kubernetes", "gitlab", "gitlab-ci", "buildkit", "kubeadm", "calico", "kustomize"),
    "github-dependabot": project("kubernetes-managed", "github", "github-actions", "buildkit", "aws", "ecr", "eks",
                                 "opentofu", "s3", "helm", "dependabot", "cloudwatch"),
    "aks-monitor": project("kubernetes-managed", "azure-repos", "azure-pipelines", "buildkit", "azure", "acr",
                           "aks", "opentofu", "azure-blob", "helm", "azure-monitor"),
    # ------------------------------------------------ plusieurs environnements
    "env-gitlab-eks": project("kubernetes-managed", "gitlab", "gitlab-ci", "buildkit", "aws", "ecr", "eks",
                              "opentofu", "s3", "helm", "cloudwatch", envs="dev-staging-prod"),
    "env-github-argo": project("kubernetes", "github", "github-actions", "buildkit", "ghcr", "k3s", "helm",
                               "argo-cd", "cosign", envs="dev-staging-prod"),
    "env-gitea-compose": project("docker-host", "gitea", "gitea-actions", "buildah", "zot", "docker-compose",
                                 "traefik", envs="staging-prod"),
    "env-jenkins-kustomize": project("kubernetes", "gitlab", "jenkins", "buildkit", "harbor", "k3s", "kustomize",
                                     envs="dev-staging-prod"),
    "env-woodpecker-flux": project("kubernetes", "gitea", "woodpecker", "buildah", "zot", "rke2", "flux",
                                   "kustomize", envs="dev-staging-prod"),
    "env-tekton-helm": project("kubernetes", "github", "tekton", "buildah", "harbor", "rke2", "helm",
                               envs="staging-prod"),
    "env-azure-aks": project("kubernetes-managed", "azure-repos", "azure-pipelines", "buildkit", "azure", "acr",
                             "aks", "opentofu", "azure-blob", "helm", envs="dev-staging-prod"),
    "env-codebuild-ecs": project("docker-host", "codecommit", "aws-codebuild", "buildkit", "aws", "ecr",
                                 "ecs-fargate", envs="dev-staging-prod"),
    "env-cloudbuild-run": project("docker-host", "github", "google-cloud-build", "buildpacks", "gcp",
                                  "artifact-registry", "cloud-run", envs="staging-prod"),
    "env-gitlab-ansible": project("vm", "gitlab", "gitlab-ci", "buildkit", "ansible", "docker-compose",
                                  envs="dev-staging-prod"),
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


def test_toutes_les_briques_de_la_matrice_sont_couvertes():
    for name, p in MATRIX.items():
        result = generate(p, CATALOG)
        assert result.ir.unsupported == [], (name, [t.name for t in result.ir.unsupported])


def test_k3s_respecte_le_cni_et_l_entree_choisis():
    files = generate(MATRIX["k3s-cilium-renovate"], CATALOG).files
    script = files["infra/cluster/install-k3s.sh"]
    assert "--flannel-backend=none" in script and "--disable-network-policy" in script
    assert "--disable traefik" in script  # Traefik est installé par le chart, pas par k3s
    install = files["platform/install.sh"]
    assert install.index("cilium/cilium") < install.index("traefik/traefik")


def test_rke2_installe_lui_meme_le_cni():
    result = generate(MATRIX["rke2-cilium"], CATALOG)
    assert "cni: cilium" in result.files["infra/cluster/install-rke2.sh"]
    assert "cilium/cilium" not in result.files.get("platform/install.sh", "")
    assert any("RKE2 installe" in n for n in result.ir.notes)


def test_kubeadm_cidr_selon_le_cni():
    script = generate(MATRIX["kubeadm-calico"], CATALOG).files["infra/cluster/install-kubeadm.sh"]
    assert "--pod-network-cidr=192.168.0.0/16" in script


def test_kind_desactive_le_cni_par_defaut():
    p = project("kubernetes", "gitlab", "gitlab-ci", "buildkit", "kind", "cilium", "helm", environment="dev")
    cfg = yaml.safe_load(generate(p, CATALOG).files["infra/cluster/kind.yaml"])
    assert cfg["networking"]["disableDefaultCNI"] is True


def test_dependabot_ecosystemes():
    doc = yaml.safe_load(generate(MATRIX["github-dependabot"], CATALOG).files[".github/dependabot.yml"])
    ecos = {u["package-ecosystem"] for u in doc["updates"]}
    assert {"pip", "docker", "github-actions", "terraform"} <= ecos


def test_cloudwatch_et_azure_monitor():
    tf = generate(MATRIX["github-dependabot"], CATALOG).files["infra/terraform/main.tf"]
    assert '"amazon-cloudwatch-observability"' in tf and "CloudWatchAgentServerPolicy" in tf
    tf = generate(MATRIX["aks-monitor"], CATALOG).files["infra/terraform/main.tf"]
    assert "oms_agent {" in tf and 'resource "azurerm_log_analytics_workspace" "main"' in tf


def test_parametres_renseignes_ecrits_dans_la_ci(tmp_path):
    p = MATRIX["github-dependabot"].clone()
    p.bricks_for("aws")[0].params = {"role_arn": "arn:aws:iam::210987654321:role/ci", "region": "eu-west-1"}
    result = generate(p, CATALOG)
    wf = yaml.safe_load(result.files[".github/workflows/pipeline.yml"])
    assert wf["env"]["IMAGE"].startswith("210987654321.dkr.ecr.eu-west-1.amazonaws.com/")
    auth = [st for job in wf["jobs"].values() for st in job["steps"]
            if st.get("uses", "").startswith("aws-actions/configure-aws-credentials")]
    assert auth and all(st["with"]["role-to-assume"] == "arn:aws:iam::210987654321:role/ci" for st in auth)
    g = project("kubernetes-managed", "gitlab", "gitlab-ci", "buildkit", "aws", "ecr", "eks", "opentofu", "s3", "helm")
    g.bricks_for("aws")[0].params = {"role_arn": "arn:aws:iam::210987654321:role/ci"}
    ci = yaml.safe_load(generate(g, CATALOG).files[".gitlab-ci.yml"])
    assert ci["variables"]["AWS_ROLE_ARN"] == "arn:aws:iam::210987654321:role/ci"
    assert ci["variables"]["AWS_ACCOUNT_ID"] == "210987654321"


# ------------------------------------------------------------- environnements
def _gen(name: str):
    return generate(MATRIX[name], CATALOG)


def test_gitlab_promotion_et_porte_d_approbation():
    ci = yaml.safe_load(_gen("env-gitlab-eks").files[".gitlab-ci.yml"])
    stages = ci["stages"]
    assert stages.index("deploy-dev") < stages.index("deploy-staging") < stages.index("deploy-production")
    prod = ci["deploy-production"]
    assert prod["environment"] == {"name": "production"}
    assert prod["rules"][0]["when"] == "manual"
    assert "when" not in ci["deploy-dev"]["rules"][0]
    assert "--namespace mon-app-dev" in "\n".join(ci["deploy-dev"]["script"])
    assert "--namespace mon-app " in "\n".join(prod["script"])


def test_github_chaine_de_promotion():
    wf = yaml.safe_load(_gen("env-github-argo").files[".github/workflows/pipeline.yml"])
    jobs = wf["jobs"]
    assert "deploy-dev" in jobs["deploy-staging"]["needs"]
    assert "deploy-staging" in jobs["deploy-production"]["needs"]
    assert jobs["deploy-production"]["environment"] == "production"
    assert "values-production.yaml" in jobs["deploy-production"]["steps"][-1]["run"]


def test_argo_cd_une_application_par_environnement():
    docs = list(yaml.safe_load_all(_gen("env-github-argo").files["deploy/argocd/application.yaml"]))
    assert [d["spec"]["destination"]["namespace"] for d in docs] == ["mon-app-dev", "mon-app-staging", "mon-app"]
    assert docs[0]["spec"]["source"]["helm"]["valueFiles"] == ["values.yaml", "values-dev.yaml"]


def test_kustomize_un_overlay_par_environnement():
    files = _gen("env-jenkins-kustomize").files
    for env, ns in [("dev", "mon-app-dev"), ("staging", "mon-app-staging"), ("production", "mon-app")]:
        overlay = yaml.safe_load(files[f"deploy/kustomize/overlays/{env}/kustomization.yaml"])
        assert overlay["namespace"] == ns
    assert "input { message 'Déployer en Production ?' }" in files["Jenkinsfile"]


def test_compose_un_hote_par_environnement():
    result = _gen("env-gitea-compose")
    names = {v.name for v in result.ir.variables}
    assert {"DEPLOY_HOST_STAGING", "DEPLOY_HOST_PRODUCTION"} <= names and "DEPLOY_HOST" not in names
    wf = yaml.safe_load(result.files[".gitea/workflows/pipeline.yml"])
    assert "-p mon-app-staging" in wf["jobs"]["deploy-staging"]["steps"][-1]["run"]


def test_ansible_un_inventaire_par_environnement():
    files = _gen("env-gitlab-ansible").files
    assert {"ansible/inventories/dev.ini", "ansible/inventories/staging.ini", "ansible/inventories/production.ini"} <= set(files)
    assert "ansible/inventory.ini" not in files


def test_ci_sans_porte_native_fichier_separe():
    files = _gen("env-codebuild-ecs").files
    assert "buildspec-deploy-production.yml" in files
    assert "mon-app-dev" in files["buildspec.yml"] and "--service mon-app --" not in files["buildspec.yml"]
    assert "--service mon-app --force-new-deployment" in files["buildspec-deploy-production.yml"]
    assert "cloudbuild-deploy-production.yaml" in _gen("env-cloudbuild-run").files
    assert "tekton/pipeline-deploy-production.yaml" in _gen("env-tekton-helm").files


def test_azure_jobs_de_deploiement():
    doc = yaml.safe_load(_gen("env-azure-aks").files["azure-pipelines.yml"])
    deploy = [st for st in doc["stages"] if st["stage"].startswith("deploy_")]
    assert [st["stage"] for st in deploy] == ["deploy_dev", "deploy_staging", "deploy_production"]
    assert deploy[-1]["jobs"][0]["environment"] == "production"


def test_woodpecker_production_sur_declenchement_manuel():
    doc = yaml.safe_load(_gen("env-woodpecker-flux").files[".woodpecker.yml"])
    prod = next(st for st in doc["steps"] if st["name"] == "deploy-production")
    assert prod["when"][0]["event"] == "manual"


def test_un_cluster_terraform_par_nom_d_environnement():
    p = MATRIX["env-gitlab-eks"].clone()
    p.bricks_for("eks")[0].params = {"cluster_name": "hors-prod"}
    p.env("production").overrides = {"eks": {"cluster_name": "prod"}}
    result = generate(p, CATALOG)
    tf = result.files["infra/terraform/main.tf"]
    assert 'module "eks_dev"' in tf and 'module "eks_production"' in tf and 'module "eks" ' not in tf
    assert tf.count('resource "aws_eks_addon"') == 2
    ci = yaml.safe_load(result.files[".gitlab-ci.yml"])
    assert "--name prod " in "\n".join(ci["deploy-production"]["script"])
    assert "--name hors-prod " in "\n".join(ci["deploy-staging"]["script"])


def test_cluster_kind_pour_dev_et_eks_pour_production():
    p = project("kubernetes-managed", "gitlab", "gitlab-ci", "buildkit", "aws", "ecr", "eks", "kind",
                "opentofu", "s3", "helm", envs="dev-staging-prod")
    for e in p.environments:
        e.cluster = "kind" if e.kind == "dev" else "eks"
    result = generate(p, CATALOG)
    ci = yaml.safe_load(result.files[".gitlab-ci.yml"])
    assert "KUBECONFIG_DATA_DEV" in "\n".join(ci["deploy-dev"]["script"])
    assert "aws eks update-kubeconfig" in "\n".join(ci["deploy-production"]["script"])
    assert "infra/cluster/kind.yaml" in result.files


def test_rapport_liste_les_environnements():
    report = _gen("env-gitlab-eks").files["PIPELINE.md"]
    assert "## Environnements" in report and "| Production (`production`) | Production | oui |" in report
