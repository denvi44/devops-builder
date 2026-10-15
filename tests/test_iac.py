# SPDX-License-Identifier: Apache-2.0
"""Lot 0.9 : Terraform / OpenTofu (état, verrous, variables, versions) et Floci."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from devops_builder import appscan
from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.ir import TOFU_VERSION
from devops_builder.model import Project, env_preset
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter
from devops_builder.suggest import suggestions

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
GOLDEN = Path(__file__).parent / "golden"


def project(target: str, *tools: str, envs: str = "staging-prod", **params) -> Project:
    p = Project(name="Boutique", target=target, environments=env_preset(envs))
    p.app.image_name = "shop"
    for t in tools:
        p.add(t, CATALOG[t].stage, **params.get(t.replace("-", "_"), {}))
    return p


def files_of(p: Project) -> dict[str, str]:
    return generate(p, CATALOG, ENGINE, allow_blocking=True).files


AWS = ("gitlab", "gitlab-ci", "buildkit", "aws", "ecr", "eks", "helm", "opentofu", "s3")
AWS_PARAMS = {"eks": {"cluster_name": "shop"}, "s3": {"bucket": "shop-tfstate"}}


# ------------------------------------------------------------------ état et verrous
def test_backend_s3_chiffre_et_verrouille():
    versions = files_of(project("kubernetes-managed", *AWS, **AWS_PARAMS))["infra/terraform/versions.tf"]
    assert 'required_version = ">= 1.10"' in versions
    assert "encrypt      = true" in versions and "use_lockfile = true" in versions
    assert 'version = "~> 6.0"' in versions


@pytest.mark.parametrize("cloud,storage,endpoint,key", [
    ("scaleway", "scaleway-object-storage", "https://s3.fr-par.scw.cloud", "SCW_ACCESS_KEY"),
    ("ovhcloud", "ovh-object-storage", "https://s3.gra.io.cloud.ovh.net", "OVH_S3_ACCESS_KEY"),
    ("outscale", "outscale-oos", "https://oos.eu-west-2.outscale.com", "OSC_ACCESS_KEY"),
])
def test_backend_compatible_s3_des_clouds_europeens(cloud, storage, endpoint, key):
    a = StarterAnswers(forge="gitlab", hosting="kubernetes-managed", cloud=cloud, envs="staging-prod",
                       secnumcloud=cloud == "outscale")
    p = build_starter(a, CATALOG)
    assert p.bricks_for(storage), "l'assistant ajoute le stockage de l'état"
    assert "R44" not in {d.rule_id for d in ENGINE.evaluate(p)}
    f = files_of(p)
    versions = f["infra/terraform/versions.tf"]
    assert f'endpoints                   = {{ s3 = "{endpoint}" }}' in versions
    assert "skip_s3_checksum            = true" in versions
    # verrou natif là où l'écriture conditionnelle est documentée (Scaleway, OVHcloud), pas chez Outscale
    assert ("use_lockfile                = true" in versions) == (cloud != "outscale")
    ci = f[".gitlab-ci.yml"]
    assert f'export AWS_ACCESS_KEY_ID="${key}"' in ci
    assert "resource_group: terraform" in ci
    if cloud == "ovhcloud":
        assert "| `OVH_S3_SECRET_KEY` | oui | à déclarer |" in f["PIPELINE.md"]


def test_etat_local_signale_et_corrige():
    p = project("kubernetes-managed", "gitlab", "gitlab-ci", "scaleway", "kapsule", "opentofu",
                kapsule={"cluster_name": "shop"})
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R44")
    assert [a.args["tool"] for a in diag.actions] == ["scaleway-object-storage"]
    assert "Backend local" in files_of(p)["infra/terraform/versions.tf"]
    # Sans CI, l'état local d'un poste n'est pas un problème
    alone = project("kubernetes-managed", "scaleway", "kapsule", "opentofu", kapsule={"cluster_name": "shop"})
    assert "R44" not in {d.rule_id for d in ENGINE.evaluate(alone)}


# ------------------------------------------------------------------ CI
def test_opentofu_installe_dans_la_ci_et_apply_serialise():
    f = files_of(project("kubernetes-managed", *AWS, **AWS_PARAMS))
    ci = yaml.safe_load(f[".gitlab-ci.yml"])
    plan, apply = ci["iac-plan"], ci["iac-apply"]
    assert plan["image"]["name"] == "alpine:3.20"  # l'image officielle n'est plus utilisable telle quelle
    assert f"tofu_{TOFU_VERSION}_linux_amd64.zip" in " ".join(plan["script"])
    assert "tofu fmt -check -recursive" in plan["script"]
    assert apply["resource_group"] == "terraform" and "resource_group" not in plan
    assert "ghcr.io/opentofu/opentofu" not in f[".gitlab-ci.yml"]


def test_github_actions_installe_les_versions_epinglees():
    tools = ("github", "github-actions", "buildkit", "aws", "ecr", "eks", "helm", "terraform", "s3")
    wf = yaml.safe_load(files_of(project("kubernetes-managed", *tools, **AWS_PARAMS))[".github/workflows/pipeline.yml"])
    plan = wf["jobs"]["iac-plan"]
    setup = next(s for s in plan["steps"] if s.get("uses", "").startswith("hashicorp/setup-terraform"))
    assert setup["with"]["terraform_version"] == "1.16.x" and setup["with"]["terraform_wrapper"] is False
    assert wf["jobs"]["iac-apply"]["concurrency"] == {"group": "terraform", "cancel-in-progress": False}
    run = next(s["run"] for s in plan["steps"] if "run" in s)
    assert "terraform fmt -check -recursive" in run


def test_variables_sans_defaut_passent_par_la_ci():
    f = files_of(project("kubernetes-managed", *AWS, "aws-rds", **AWS_PARAMS))
    variables = f["infra/terraform/variables.tf"]
    for name in ("vpc_id", "subnet_ids", "db_subnet_group", "db_security_group_ids"):
        assert variables.count(f'variable "{name}"') == 1
        assert f"| `TF_VAR_{name}` | non | à déclarer |" in f["PIPELINE.md"]
        assert re.search(rf"^{name} = ", f["infra/terraform/terraform.tfvars.example"], re.M)
    assert "terraform.tfvars" in f["infra/terraform/.gitignore"] and "*.tfstate" in f["infra/terraform/.gitignore"]


def test_projet_ovh_renseigne_reprend_la_valeur():
    p = project("kubernetes-managed", "gitlab", "gitlab-ci", "ovhcloud", "ovh-mks", "opentofu", "ovh-object-storage",
                ovhcloud={"service_name": "a" * 32}, ovh_mks={"cluster_name": "shop"},
                ovh_object_storage={"bucket": "shop-tfstate"})
    assert f'default     = "{"a" * 32}"' in files_of(p)["infra/terraform/variables.tf"]


def test_sorties_des_clusters_et_registres():
    outputs = files_of(project("kubernetes-managed", *AWS, **AWS_PARAMS))["infra/terraform/outputs.tf"]
    assert "module.eks.cluster_endpoint" in outputs and "aws_ecr_repository.app.repository_url" in outputs
    scw = build_starter(StarterAnswers(forge="gitlab", hosting="kubernetes-managed", cloud="scaleway"), CATALOG)
    f = files_of(scw)
    assert "scaleway_k8s_cluster.main.apiserver_url" in f["infra/terraform/outputs.tf"]
    assert "data.scaleway_k8s_version.latest.name" in f["infra/terraform/main.tf"]


def test_tflint_et_infracost():
    f = files_of(project("kubernetes-managed", *AWS, "tflint", "infracost", **AWS_PARAMS))
    ci = yaml.safe_load(f[".gitlab-ci.yml"])
    assert ci["tflint"]["script"] == ["tflint --chdir=infra/terraform --init",
                                      "tflint --chdir=infra/terraform --format compact"]
    assert ci["infracost"]["allow_failure"] is True
    assert 'preset  = "recommended"' in f["infra/terraform/.tflint.hcl"]
    assert "| `INFRACOST_API_KEY` | oui | à déclarer |" in f["PIPELINE.md"]
    assert suggestions(project("docker-host", "opentofu"), CATALOG, "opentofu")[0].id == "tflint"


def test_aucune_ancre_yaml_dans_les_fichiers_generes():
    for path in GOLDEN.rglob("*.y*ml"):
        assert "&id0" not in path.read_text(encoding="utf-8"), path


# ------------------------------------------------------------------ Floci
def test_floci_environnement_local_et_tests_de_l_application():
    f = files_of(project("docker-host", "gitlab", "gitlab-ci", "unit-tests", "floci"))
    compose = yaml.safe_load(f["dev/floci/compose.yaml"])
    floci = compose["services"]["floci"]
    assert floci["image"].startswith("floci/floci:") and floci["ports"] == ["4566:4566"]
    assert "/var/run/docker.sock:/var/run/docker.sock" in floci["volumes"]
    assert "AWS_ENDPOINT_URL=http://localhost:4566" in f["dev/floci/aws.env"]
    unit = yaml.safe_load(f[".gitlab-ci.yml"])["unit-tests"]
    assert unit["services"][0]["alias"] == "floci" and unit["services"][0]["variables"]["FLOCI_HOSTNAME"] == "floci"
    assert unit["variables"]["AWS_ENDPOINT_URL"] == "http://floci:4566"
    assert "scripts/tf-floci.sh" not in f  # pas de pile AWS


def test_floci_dans_github_et_woodpecker():
    gh = yaml.safe_load(files_of(project("docker-host", "github", "github-actions", "unit-tests", "floci"))
                        [".github/workflows/pipeline.yml"])
    unit = gh["jobs"]["unit-tests"]
    assert unit["services"]["floci"]["ports"] == ["4566:4566"] and "container" in unit
    assert unit["env"]["AWS_ENDPOINT_URL"] == "http://floci:4566"
    wp = yaml.safe_load(files_of(project("docker-host", "gitea", "woodpecker", "unit-tests", "floci"))[".woodpecker.yml"])
    assert wp["services"][0]["name"] == "floci"
    step = next(s for s in wp["steps"] if s["name"] == "unit-tests")
    assert step["environment"]["AWS_ENDPOINT_URL"] == "http://floci:4566"


def test_floci_sans_conteneurs_annexes_le_dit():
    f = files_of(project("docker-host", "gitlab", "jenkins", "unit-tests", "floci"))
    assert "floci:4566" not in f["Jenkinsfile"]
    assert "Floci n'est pas démarré par Jenkins" in f["PIPELINE.md"]


def test_floci_plan_de_la_pile_aws(tmp_path):
    p = project("kubernetes-managed", *AWS, "aws-rds", "floci", **AWS_PARAMS)
    f = files_of(p)
    job = yaml.safe_load(f[".gitlab-ci.yml"])["iac-floci"]
    assert job["allow_failure"] is True and job["variables"]["FLOCI_ENDPOINT"] == "http://floci:4566"
    assert job["script"][-1] == "bash scripts/tf-floci.sh plan"
    script = f["scripts/tf-floci.sh"]
    assert 'backend "local" {}' in script and 's3_use_path_style           = true' in script
    assert 'db_subnet_group = "floci"' in script and "vpc_id = " in script
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0
    if shutil.which("shellcheck"):
        r = subprocess.run(["shellcheck", "-S", "warning", "-"], input=script, text=True, capture_output=True)
        assert r.returncode == 0, r.stdout
    # Pile multi-cloud : pas de plan sur Floci
    multi = project("kubernetes-managed", *AWS, "gcp", "floci", **AWS_PARAMS)
    assert "scripts/tf-floci.sh" not in files_of(multi)


def test_analyse_propose_floci(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "requirements.txt").write_text("fastapi\nboto3\n")
    profile = appscan.scan(root)
    assert profile.aws_sdk and profile.aws_emulator is None
    offers = dict(appscan.proposed_bricks(profile, project("docker-host", "gitlab"), CATALOG))
    assert "SDK AWS" in offers["floci"]
    (root / "docker-compose.yml").write_text("services:\n  aws:\n    image: localstack/localstack:3\n")
    profile = appscan.scan(root)
    assert profile.aws_emulator == "localstack"
    assert "LocalStack" in dict(appscan.proposed_bricks(profile, project("docker-host", "gitlab"), CATALOG))["floci"]


# ------------------------------------------------------------------ validation réelle (facultative)
MIRROR = os.environ.get("DEVOPS_BUILDER_TOFU_MIRROR")


@pytest.mark.skipif(not (MIRROR and shutil.which("tofu")), reason="miroir de providers OpenTofu non configuré")
def test_toutes_les_piles_passent_tofu_validate(tmp_path):
    """DEVOPS_BUILDER_TOFU_MIRROR=dossier d'un filesystem_mirror (aws, google, azurerm, ovh, scaleway, outscale, random)."""
    rc = tmp_path / "tofurc"
    rc.write_text(f'plugin_cache_dir = "{tmp_path / "cache"}"\nprovider_installation {{\n  filesystem_mirror {{\n'
                  f'    path = "{MIRROR}"\n  }}\n}}\n')
    (tmp_path / "cache").mkdir()
    stub = tmp_path / "eks"
    stub.mkdir()
    stub.joinpath("main.tf").write_text("".join(f'variable "{v}" {{\n  default = null\n}}\n' for v in (
        "name", "kubernetes_version", "vpc_id", "subnet_ids", "eks_managed_node_groups"))
        + 'output "cluster_name" {\n  value = "x"\n}\noutput "cluster_endpoint" {\n  value = "x"\n}\n')
    failures = []
    for stack in sorted(GOLDEN.glob("*/infra/terraform")):
        work = tmp_path / stack.parent.parent.name
        shutil.copytree(stack, work)
        for tf in work.glob("*.tf"):
            tf.write_text(re.sub(r'source\s+=\s+"terraform-aws-modules/eks/aws"\n\s+version\s+=\s+"[^"]+"',
                                 f'source = "{stub}"', tf.read_text()))
        env = {**os.environ, "TF_CLI_CONFIG_FILE": str(rc)}
        for args in (["init", "-backend=false", "-input=false", "-no-color"], ["validate", "-no-color"]):
            r = subprocess.run(["tofu", *args], cwd=work, env=env, capture_output=True, text=True)
            if r.returncode:
                failures.append(f"{stack.parent.parent.name} : {(r.stdout + r.stderr)[-600:]}")
                break
    assert not failures, "\n".join(failures)
