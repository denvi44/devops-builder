# SPDX-License-Identifier: Apache-2.0
"""Droits des deux identités de la CI sur chaque cloud.

Les jobs d'infrastructure (plan, apply) prennent une identité aux droits étendus : la pile crée des réseaux, des
clusters et des rôles. Les autres jobs (build, publication, déploiement) en prennent une seconde, limitée à ce
qu'ils font réellement, déduit des étapes générées : pousser l'image dans le registre du cloud, obtenir l'accès au
cluster, mettre à jour un service managé, lire les sorties de l'état Terraform pour trouver les machines.
"""

from __future__ import annotations

import json

from ..ir import IR

BUILD_STAGES = ("test", "build", "security", "publish")
KUBE_TOOLS = ("helm", "kustomize")
STATE_TOOLS = ("docker-compose", "ansible")  # déploiement qui lit la sortie « hosts » de la pile


def needs(ir: IR, cloud: str) -> set[str]:
    """Ce que font les jobs hors infrastructure sur ce cloud : registry, kube, ecs, run, aca, state."""
    out: set[str] = set()
    for st in ir.steps:
        if cloud not in st.cloud or st.stage == "infra":
            continue
        if st.stage in BUILD_STAGES:
            out.add("registry")
        elif st.tool in KUBE_TOOLS:
            out.add("kube")
        elif st.tool == "ecs-fargate":
            out.add("ecs")
        elif st.tool == "cloud-run":
            out.add("run")
        elif st.tool == "azure-container-apps":
            out.add("aca")
        elif st.tool in STATE_TOOLS:
            out.add("state")
    return out


def _envs_params(ir: IR, tool: str) -> list[dict]:
    seen, out = set(), []
    for env in ir.envs:
        p = ir.params(tool, env)
        key = json.dumps(p, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def aws_policy(ir: IR) -> dict:
    """Politique de l'identité de déploiement AWS ; ${AWS_ACCOUNT_ID} est remplacé par le shell."""
    n = needs(ir, "aws")
    region = ir.params("aws").get("region", "eu-west-3")
    acct = "${AWS_ACCOUNT_ID}"
    statements: list[dict] = []
    if "registry" in n and ir.registry and ir.registry.id == "ecr":
        repo = ir.params("ecr").get("repository", ir.app)
        statements += [
            {"Sid": "EcrConnexion", "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
            {"Sid": "EcrImage", "Effect": "Allow",
             "Action": ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload",
                        "ecr:DescribeImages", "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload",
                        "ecr:PutImage", "ecr:UploadLayerPart"],
             "Resource": f"arn:aws:ecr:{region}:{acct}:repository/{repo}"}]
    if "kube" in n:
        clusters = sorted({str(p.get("cluster_name", "mon-cluster")) for p in _envs_params(ir, "eks")})
        statements.append({"Sid": "EksKubeconfig", "Effect": "Allow", "Action": "eks:DescribeCluster",
                           "Resource": [f"arn:aws:eks:{region}:{acct}:cluster/{c}" for c in clusters]})
    if "ecs" in n:
        services = sorted({f"{p.get('cluster')}/{p.get('service')}" for p in _envs_params(ir, "ecs-fargate")})
        statements.append({"Sid": "EcsDeploiement", "Effect": "Allow",
                           "Action": ["ecs:DescribeServices", "ecs:UpdateService"],
                           "Resource": [f"arn:aws:ecs:{region}:{acct}:service/{s}" for s in services]})
    if "state" in n and ir.has("s3"):
        bucket = ir.params("s3").get("bucket")
        statements += [
            {"Sid": "EtatLecture", "Effect": "Allow", "Action": "s3:GetObject",
             "Resource": f"arn:aws:s3:::{bucket}/{ir.app}/terraform.tfstate"},
            {"Sid": "EtatListe", "Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{bucket}"}]
    return {"Version": "2012-10-17", "Statement": statements}


def gcp_roles(ir: IR) -> list[str]:
    n = needs(ir, "gcp")
    roles = []
    if "registry" in n and ir.registry and ir.registry.id in ("artifact-registry", "gcr"):
        roles.append("roles/artifactregistry.writer")
    if "kube" in n:
        roles.append("roles/container.developer")
    if "run" in n:
        roles += ["roles/run.developer", "roles/iam.serviceAccountUser"]
    if "state" in n and ir.has("gcs"):
        roles.append("roles/storage.objectViewer")
    return roles


def azure_roles(ir: IR) -> list[tuple[str, str]]:
    """(rôle, portée) : la portée est le groupe de ressources du projet, jamais l'abonnement."""
    n = needs(ir, "azure")
    roles = []
    if "registry" in n and ir.registry and ir.registry.id == "acr":
        roles.append(("AcrPush", "rg"))
    if "kube" in n:
        roles.append(("Azure Kubernetes Service Cluster User Role", "rg"))
    if "aca" in n:
        roles.append(("Contributor", "rg"))  # mise à jour de l'application Container Apps du groupe
    if "state" in n and ir.has("azure-blob"):
        roles.append(("Reader and Data Access", "rg"))  # clés du compte de stockage de l'état, lecture
    return roles


def deploy_summary(ir: IR, cloud: str) -> str:
    labels = {"registry": "pousser l'image", "kube": "obtenir l'accès au cluster", "ecs": "mettre à jour le service ECS",
              "run": "déployer sur Cloud Run", "aca": "mettre à jour Container Apps",
              "state": "lire les sorties de l'état Terraform"}
    items = [labels[k] for k in ("registry", "kube", "ecs", "run", "aca", "state") if k in needs(ir, cloud)]
    return ", ".join(items) if items else "aucun droit sur ce cloud"
