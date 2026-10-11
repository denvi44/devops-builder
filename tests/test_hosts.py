"""Lot 0.11 : machines créées par Terraform, inventaire Ansible et déploiement SSH tirés de ses sorties."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import textwrap

import pytest
import yaml

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.generators.hosts import COMPUTE
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter, host_clouds, validate

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
RESOURCES = {"aws": "aws_instance", "gcp": "google_compute_instance", "azure": "azurerm_linux_virtual_machine",
             "scaleway": "scaleway_instance_server", "ovhcloud": "ovh_cloud_project_instance", "outscale": "outscale_vm"}


def starter(hosting: str, cloud: str | None, envs: str = "dev-recette-prod", **kw):
    a = StarterAnswers(forge="gitlab", hosting=hosting, cloud=cloud, envs=envs, secnumcloud=cloud == "outscale", **kw)
    assert not validate(a)
    return build_starter(a, CATALOG)


@pytest.mark.parametrize("cloud", list(RESOURCES))
@pytest.mark.parametrize("hosting", ["vm", "docker-host"])
def test_machines_creees_et_chainees(cloud, hosting):
    p = starter(hosting, cloud, shared_host=True)
    compute = CATALOG[cloud].services["compute"]
    assert p.bricks_for(compute) and p.bricks_for("opentofu") and p.bricks_for(CATALOG[cloud].services["object-storage"])
    assert not RuleEngine.blocking(ENGINE.evaluate(p))
    assert not any(d.rule_id == "R34" and "Hôtes de l'application" in d.message for d in ENGINE.evaluate(p))
    result = generate(p, CATALOG, ENGINE)
    f = result.files
    main = f["infra/terraform/main.tf"]
    # dev et recette partagent « hors-production » : deux groupes de machines, pas trois
    assert main.count(f'resource "{RESOURCES[cloud]}" ') == 2
    assert '"hors-production"' in f["infra/terraform/outputs.tf"] and '"production"' in f["infra/terraform/outputs.tf"]
    assert "docker-compose-v2" in main and "ssh_authorized_keys" in main
    assert 'variable "ssh_public_key"' in f["infra/terraform/variables.tf"]
    assert "| `TF_VAR_ssh_public_key` | non | à déclarer |" in f["PIPELINE.md"]
    ci = yaml.safe_load(f[".gitlab-ci.yml"])
    script = " ".join(ci["deploy-recette"]["script"])
    if hosting == "vm":
        assert "bash scripts/tf-inventory.sh recette" in script
        assert script.index("tf-inventory.sh") < script.index("ansible-playbook")
        assert "Machines créées par Terraform" in f["ansible/inventories/recette.ini"]
    else:
        assert 'export DEPLOY_HOST_RECETTE="deploy@$(bash scripts/tf-inventory.sh --first recette)"' in script
        assert "DEPLOY_HOST_RECETTE` |" not in f["PIPELINE.md"]  # plus à déclarer
    assert compute not in [t.id for t in result.ir.unsupported]


def test_serveurs_existants_restent_possibles():
    p = starter("vm", None, envs="prod")
    assert not any(p.bricks_for(t) for t in COMPUTE)
    assert "scripts/tf-inventory.sh" not in generate(p, CATALOG, ENGINE, allow_blocking=True).files


def test_secnumcloud_limite_les_clouds_des_machines():
    assert host_clouds("vm", True) == ["ovhcloud", "outscale"]
    assert host_clouds("kubernetes", False) == []
    bad = StarterAnswers(hosting="docker-host", cloud="aws", secnumcloud=True)
    assert validate(bad)


def test_machines_sans_iac_demandent_terraform():
    from devops_builder.model import Project
    p = Project(target="vm")
    for t in ("aws", "aws-ec2", "ansible"):
        p.add(t, CATALOG[t].stage)
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R29")
    assert {a.args["tool"] for a in diag.actions} >= {"opentofu", "terraform"}


@pytest.mark.skipif(not shutil.which("jq") and not shutil.which("bash"), reason="bash et jq requis")
def test_script_d_inventaire(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq absent")
    p = starter("vm", "scaleway", shared_host=True)
    generate(p, CATALOG, ENGINE).write(tmp_path)
    fake = tmp_path / "bin" / "tofu"
    fake.parent.mkdir()
    outputs = {"hors-production": ["203.0.113.10", "203.0.113.11"], "production": ["198.51.100.5"]}
    fake.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        if [ "$1" = output ]; then echo '{json.dumps(outputs)}'; fi
        """))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "infra/terraform/.terraform").mkdir()
    env = {**os.environ, "PATH": f"{fake.parent}:{os.environ['PATH']}"}
    run = lambda *a: subprocess.run(["bash", "scripts/tf-inventory.sh", *a], cwd=tmp_path, env=env,  # noqa: E731
                                    capture_output=True, text=True)
    r = run("recette")
    assert r.returncode == 0, r.stderr
    inv = (tmp_path / "ansible/inventories/recette.ini").read_text()
    assert "[app]\n203.0.113.10\n203.0.113.11\n" in inv and "deploy_env=recette" in inv
    assert run("--first", "production").stdout.strip() == "198.51.100.5"
    outputs.pop("production")
    fake.write_text(fake.read_text().replace('"production": ["198.51.100.5"]', '"autre": []'))
    r = run("production")
    assert r.returncode == 1 and "lancer d'abord l'apply" in r.stderr
    if shutil.which("shellcheck"):
        sc = subprocess.run(["shellcheck", "-S", "warning", "scripts/tf-inventory.sh"], cwd=tmp_path,
                            capture_output=True, text=True)
        assert sc.returncode == 0, sc.stdout


def test_hotes_preparation_n_ecrase_pas_docker():
    site = yaml.safe_load(generate(starter("vm", "aws"), CATALOG, ENGINE).files["ansible/site.yml"])
    tasks = site[0]["tasks"]
    assert tasks[0]["ansible.builtin.stat"]["path"] == "/usr/bin/docker"
    assert all("not docker_bin.stat.exists" in t["when"] for t in tasks if "block" in t)
