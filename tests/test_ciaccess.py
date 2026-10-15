# SPDX-License-Identifier: Apache-2.0
"""Deux identités de CI par cloud : infrastructure (plan, apply) et déploiement aux droits limités."""

from __future__ import annotations

import json
import re

import yaml
from test_rules import CATALOG

from devops_builder.generators import ciaccess, render
from devops_builder.ir import build_ir
from devops_builder.starter import StarterAnswers, build_starter


def _p(forge="gitlab", cloud="aws", hosting="kubernetes-managed"):
    return build_starter(StarterAnswers(forge=forge, hosting=hosting, cloud=cloud, envs="staging-prod"), CATALOG)


def test_jobs_d_infrastructure_avec_leur_identite_gitlab():
    files, ir = render(_p(), CATALOG)
    ci = yaml.safe_load(files[".gitlab-ci.yml"])
    assert 'export AWS_ROLE_ARN="$AWS_INFRA_ROLE_ARN"' in ci["iac-apply"]["script"][0]
    assert not any("AWS_INFRA_ROLE_ARN" in line for line in ci["deploy-staging"]["script"])
    assert {v.name for v in ir.variables} >= {"AWS_ROLE_ARN", "AWS_INFRA_ROLE_ARN"}


def test_jobs_d_infrastructure_avec_leur_identite_github():
    for cloud, key, var in (("aws", "role-to-assume", "AWS_INFRA_ROLE_ARN"),
                            ("gcp", "service_account", "GCP_INFRA_SERVICE_ACCOUNT"),
                            ("azure", "client-id", "AZURE_INFRA_CLIENT_ID")):
        files, _ = render(_p("github", cloud), CATALOG)
        jobs = yaml.safe_load(files[".github/workflows/pipeline.yml"])["jobs"]
        login = next(s for s in jobs["iac-apply"]["steps"] if key in s.get("with", {}))
        assert login["with"][key] == "${{ vars." + var + " }}", cloud
        deploy = next(s for s in jobs["deploy-staging"]["steps"] if key in s.get("with", {}))
        assert var not in deploy["with"][key], cloud


def test_politique_aws_de_deploiement_limitee():
    ir = build_ir(_p(), CATALOG)
    assert ciaccess.needs(ir, "aws") == {"registry", "kube"}
    policy = ciaccess.aws_policy(ir)
    actions = {a for s in policy["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])}
    assert "eks:DescribeCluster" in actions and "ecr:PutImage" in actions
    assert not any(a.endswith("*") or a.startswith("iam:") for a in actions)
    assert all(s["Resource"] != "*" for s in policy["Statement"] if s["Action"] != "ecr:GetAuthorizationToken")


def test_mode_d_emploi_deux_roles_et_confiance_valide():
    files, _ = render(_p(), CATALOG)
    guide = files["docs/mise-en-route.md"]
    assert "--role-name mon-app-ci " in guide and "--role-name mon-app-ci-infra " in guide
    assert "AdministratorAccess" in guide.split("mon-app-ci-infra", 1)[1]
    for block in re.findall(r"<<EOF\n(.*?)\nEOF", guide, flags=re.S):
        doc = json.loads(block.replace("${AWS_ACCOUNT_ID}", "123456789012").replace("${REPO}", "g/p"))
        if "Statement" in doc and doc["Statement"] and "Condition" in doc["Statement"][0]:
            cond = doc["Statement"][0]["Condition"]
            # aud et sub dans le même opérateur avec GitLab (deux clés StringEquals se seraient écrasées)
            assert set(cond["StringEquals"]) == {"gitlab.com:aud", "gitlab.com:sub"}


def test_github_l_identite_d_infrastructure_reservee_au_plan_et_a_l_apply():
    files, _ = render(_p("github"), CATALOG)
    guide = files["docs/mise-en-route.md"]
    infra = guide.split("trust-infra.json <<EOF\n", 1)[1].split("\nEOF", 1)[0]
    subs = json.loads(infra.replace("${AWS_ACCOUNT_ID}", "1"))["Statement"][0]["Condition"]["StringLike"]
    assert subs["token.actions.githubusercontent.com:sub"] == [
        "repo:${REPO}:ref:refs/heads/main", "repo:${REPO}:pull_request", "repo:${REPO}:environment:production"]


def test_acces_eks_du_role_de_deploiement():
    p = _p()
    p.bricks_for("aws")[0].params["role_arn"] = "arn:aws:iam::123456789012:role/mon-app-ci"
    files, _ = render(p, CATALOG)
    main = files["infra/terraform/main.tf"]
    assert "enable_cluster_creator_admin_permissions = true" in main and "AmazonEKSClusterAdminPolicy" in main
    assert 'default     = "arn:aws:iam::123456789012:role/mon-app-ci"' in files["infra/terraform/variables.tf"]
    assert 'variable "cluster_admin_arns"' in files["infra/terraform/variables.tf"]


def test_gcp_et_azure_roles_de_deploiement():
    assert ciaccess.gcp_roles(build_ir(_p(cloud="gcp"), CATALOG)) == ["roles/artifactregistry.writer",
                                                                       "roles/container.developer"]
    roles = ciaccess.azure_roles(build_ir(_p(cloud="azure"), CATALOG))
    assert ("AcrPush", "rg") in roles and ("Azure Kubernetes Service Cluster User Role", "rg") in roles
    files, _ = render(_p(cloud="azure"), CATALOG)
    guide = files["docs/mise-en-route.md"]
    assert "/resourceGroups/" in guide.split("APP_ID=", 1)[1]
