"""Génération Terraform / OpenTofu : fournisseurs, backend d'état et services managés."""

from __future__ import annotations

from ..ir import IR
from .common import HEADER

DIR = "infra/terraform"

PROVIDER_SOURCES = {
    "aws": ("hashicorp/aws", "~> 5.0"),
    "gcp": ("hashicorp/google", "~> 6.0"),
    "azure": ("hashicorp/azurerm", "~> 4.0"),
    "ovhcloud": ("ovh/ovh", "~> 1.0"),
    "outscale": ("outscale/outscale", "~> 1.0"),
    "scaleway": ("scaleway/scaleway", "~> 2.0"),
}
PROVIDER_LOCAL = {"aws": "aws", "gcp": "google", "azure": "azurerm", "ovhcloud": "ovh",
                  "outscale": "outscale", "scaleway": "scaleway"}


def _providers_block(ir: IR) -> str:
    lines = []
    for p in ir.providers:
        params = ir.params(p.id)
        if p.id == "aws":
            lines.append(f'provider "aws" {{\n  region = "{params.get("region", "eu-west-3")}"\n}}')
        elif p.id == "gcp":
            lines.append(f'provider "google" {{\n  project = var.gcp_project_id\n  region  = "{params.get("region", "europe-west9")}"\n}}')
        elif p.id == "azure":
            lines.append('provider "azurerm" {\n  features {}\n}')
        elif p.id == "ovhcloud":
            lines.append(f'provider "ovh" {{\n  endpoint = "{params.get("endpoint", "ovh-eu")}"\n}}')
        elif p.id == "outscale":
            lines.append(f'provider "outscale" {{\n  region = "{params.get("region", "eu-west-2")}"\n}}')
        elif p.id == "scaleway":
            lines.append(f'provider "scaleway" {{\n  region = "{params.get("region", "fr-par")}"\n  zone   = "{params.get("zone", "fr-par-1")}"\n}}')
    return "\n\n".join(lines)


def _backend(ir: IR) -> str:
    if ir.has("s3"):
        b = ir.params("s3")
        region = ir.params("aws").get("region", "eu-west-3")
        return (f'  backend "s3" {{\n    bucket = "{b.get("bucket")}"\n    key    = "{ir.app}/terraform.tfstate"\n'
                f'    region = "{region}"\n  }}')
    if ir.has("gcs"):
        b = ir.params("gcs")
        return f'  backend "gcs" {{\n    bucket = "{b.get("bucket")}"\n    prefix = "{ir.app}"\n  }}'
    if ir.has("azure-blob"):
        b = ir.params("azure-blob")
        rg = ir.params("azure").get("resource_group", "rg-mon-projet")
        return (f'  backend "azurerm" {{\n    resource_group_name  = "{rg}"\n'
                f'    storage_account_name = "{b.get("storage_account")}"\n    container_name       = "{b.get("container")}"\n'
                f'    key                  = "{ir.app}.tfstate"\n  }}')
    return "  # Backend local : ajouter un stockage objet (S3, GCS, Blob) pour partager l'état."


CLUSTER_TOOLS = ("eks", "gke", "aks", "ovh-mks", "kapsule")


def cluster_instances(ir: IR, tool_id: str) -> list[tuple[str, dict]]:
    """(suffixe d'étiquette, paramètres) par nom de cluster distinct entre environnements.

    Un seul nom → un seul cluster partagé (étiquettes inchangées). Plusieurs noms (surcharge
    « Nom du cluster » par environnement) → un bloc par cluster, suffixé par l'environnement.
    """
    envs = [e for e in ir.envs if (c := ir.cluster_for(e)) is not None and c.id == tool_id]
    if not envs:
        return [("", ir.params(tool_id))]
    by_name: dict[str, tuple[str, dict]] = {}
    for env in envs:
        params = ir.params(tool_id, env)
        by_name.setdefault(str(params.get("cluster_name")), ("_" + env.id.replace("-", "_"), params))
    if len(by_name) == 1:
        return [("", next(iter(by_name.values()))[1])]
    return list(by_name.values())


def _resource(ir: IR, tool_id: str, p: dict | None = None, sfx: str = "", first: bool = True) -> str | None:
    p = ir.params(tool_id) if p is None else p
    app = ir.app
    if tool_id == "eks":
        cw_policy = cw_addon = ""
        if ir.has("cloudwatch"):
            cw_policy = ('\n\n      iam_role_additional_policies = {\n'
                         '        CloudWatchAgentServerPolicy = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"\n'
                         '      }')
            cw_addon = ('\n\n# --- Amazon CloudWatch (Container Insights)\n'
                        f'resource "aws_eks_addon" "cloudwatch{sfx}" {{\n'
                        f'  cluster_name = module.eks{sfx}.cluster_name\n'
                        '  addon_name   = "amazon-cloudwatch-observability"\n}')
            ir.cover("cloudwatch")
        return f'''module "eks{sfx}" {{
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "{p.get("cluster_name")}"
  cluster_version = "{p.get("version", "1.33")}"
  vpc_id          = var.vpc_id
  subnet_ids      = var.subnet_ids

  eks_managed_node_groups = {{
    default = {{
      instance_types = ["t3.large"]
      min_size       = 2
      max_size       = 4
      desired_size   = 2{cw_policy}
    }}
  }}
}}{cw_addon}'''
    if tool_id == "ecr":
        return f'resource "aws_ecr_repository" "app" {{\n  name                 = "{p.get("repository", app)}"\n  image_tag_mutability = "IMMUTABLE"\n\n  image_scanning_configuration {{\n    scan_on_push = true\n  }}\n}}'
    if tool_id == "aws-secrets-manager":
        return f'resource "aws_secretsmanager_secret" "app" {{\n  name = "{app}"\n}}'
    if tool_id in ("s3", "gcs"):
        return (f"# Le bucket {p.get('bucket')} porte l'état de cette pile : il est créé à part (amorçage),\n"
                "# pas par la pile qui l'utilise.")
    if tool_id == "gke":
        if ir.has("cloud-monitoring") and first:
            ir.notes.append("Cloud Monitoring et Cloud Logging sont actifs par défaut sur GKE Autopilot : rien à installer.")
            ir.cover("cloud-monitoring")
        return f'''resource "google_container_cluster" "main{sfx}" {{
  name     = "{p.get("cluster_name")}"
  location = "{p.get("region", "europe-west9")}"

  enable_autopilot    = true
  deletion_protection = true
}}'''
    if tool_id in ("artifact-registry", "gcr"):
        region = ir.params("gcp").get("region", "europe-west9")
        return (f'resource "google_artifact_registry_repository" "app" {{\n  location      = "{region}"\n'
                f'  repository_id = "{p.get("repository", app)}"\n  format        = "DOCKER"\n}}')
    if tool_id == "gcp-secret-manager":
        return f'resource "google_secret_manager_secret" "app" {{\n  secret_id = "{app}"\n\n  replication {{\n    auto {{}}\n  }}\n}}'
    if tool_id in ("aks", "acr", "azure-key-vault", "azure-blob", "azure-container-apps"):
        return _azure(ir, tool_id, p, sfx, first)
    if tool_id == "ovh-mks":
        return (f'resource "ovh_cloud_project_kube" "main{sfx}" {{\n  service_name = var.ovh_service_name\n'
                f'  name         = "{p.get("cluster_name")}"\n  region       = "{p.get("region", "GRA11")}"\n}}')
    if tool_id == "kapsule":
        return f'''resource "scaleway_k8s_cluster" "main{sfx}" {{
  name                        = "{p.get("cluster_name")}"
  version                     = "1.32"
  cni                         = "cilium"
  delete_additional_resources = false
}}

resource "scaleway_k8s_pool" "default{sfx}" {{
  cluster_id = scaleway_k8s_cluster.main{sfx}.id
  name       = "default"
  node_type  = "DEV1-M"
  size       = 2
}}'''
    if tool_id == "scaleway-registry":
        return f'resource "scaleway_registry_namespace" "app" {{\n  name = "{p.get("namespace", app)}"\n}}'
    if tool_id == "oks":
        return ("# OKS (Outscale Kubernetes as a Service) : à créer via la console ou l'API OKS ;\n"
                "# vérifier la prise en charge par le provider outscale/outscale avant de l'automatiser ici.")
    return None


def _azure(ir: IR, tool_id: str, p: dict, sfx: str = "", first: bool = True) -> str:
    app = ir.app
    loc = ir.params("azure").get("location", "francecentral")
    if tool_id == "aks":
        oms = workspace = ""
        dns = app + sfx.replace("_", "-")
        if ir.has("azure-monitor"):
            oms = ("\n\n  oms_agent {\n    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id\n  }")
            workspace = ('\n\n# --- Azure Monitor (Container Insights)\n'
                         'resource "azurerm_log_analytics_workspace" "main" {\n'
                         f'  name                = "log-{app}"\n'
                         '  location            = azurerm_resource_group.main.location\n'
                         '  resource_group_name = azurerm_resource_group.main.name\n'
                         '  sku                 = "PerGB2018"\n'
                         '  retention_in_days   = 30\n}')
            ir.cover("azure-monitor")
            if not first:
                workspace = ""  # un espace Log Analytics partagé par les clusters
        return f'''resource "azurerm_kubernetes_cluster" "main{sfx}" {{
  name                = "{p.get("cluster_name")}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "{dns}"

  default_node_pool {{
    name       = "default"
    node_count = 2
    vm_size    = "Standard_D2s_v5"
  }}

  identity {{
    type = "SystemAssigned"
  }}{oms}
}}{workspace}'''
    if tool_id == "acr":
        return (f'resource "azurerm_container_registry" "main" {{\n  name                = "{p.get("registry_name", "monappregistry")}"\n'
                f'  resource_group_name = azurerm_resource_group.main.name\n  location            = azurerm_resource_group.main.location\n'
                f'  sku                 = "Standard"\n}}')
    if tool_id == "azure-key-vault":
        return (f'data "azurerm_client_config" "current" {{}}\n\nresource "azurerm_key_vault" "main" {{\n'
                f'  name                = "{p.get("vault_name", "kv-" + app)}"\n  location            = azurerm_resource_group.main.location\n'
                f'  resource_group_name = azurerm_resource_group.main.name\n'
                f'  tenant_id           = data.azurerm_client_config.current.tenant_id\n  sku_name            = "standard"\n}}')
    if tool_id == "azure-blob":
        return f'# Le compte de stockage de l\'état est créé hors de cette pile (amorçage), région {loc}.'
    if tool_id == "azure-container-apps":
        return "# Azure Container Apps : ajouter azurerm_container_app_environment et azurerm_container_app."
    return ""


# Ressources pour lesquelles seul un commentaire est écrit : elles restent à configurer.
COMMENT_ONLY = {"oks", "azure-container-apps"}

IAC_RESOURCES = {
    "eks", "ecr", "aws-secrets-manager", "s3", "gke", "artifact-registry", "gcr", "gcp-secret-manager",
    "gcs", "aks", "acr", "azure-key-vault", "azure-blob", "azure-container-apps", "ovh-mks", "kapsule",
    "scaleway-registry", "oks",
}


def terraform(ir: IR) -> dict[str, str]:
    from . import data
    if not ir.providers and not any(ir.has(t) for t in IAC_RESOURCES):
        return {}
    db_blocks, db_variables, db_outputs = data.terraform_blocks(ir)
    required = []
    for p in ir.providers:
        src, ver = PROVIDER_SOURCES.get(p.id, (p.terraform_provider, ">= 0"))
        required.append(f'    {PROVIDER_LOCAL.get(p.id, p.id)} = {{\n      source  = "{src}"\n      version = "{ver}"\n    }}')
    if data.needs_random(ir):
        required.append('    random = {\n      source  = "hashicorp/random"\n      version = "~> 3.6"\n    }')
    versions = (f"# {HEADER}\nterraform {{\n  required_version = \">= 1.6\"\n\n  required_providers {{\n"
                + "\n".join(required) + "\n  }\n\n" + _backend(ir) + "\n}\n")
    main_parts = [f"# {HEADER}", _providers_block(ir)]
    if ir.has("azure"):
        rg = ir.params("azure").get("resource_group", "rg-mon-projet")
        loc = ir.params("azure").get("location", "francecentral")
        main_parts.append(f'resource "azurerm_resource_group" "main" {{\n  name     = "{rg}"\n  location = "{loc}"\n}}')
    for _, b in ir.project.all_bricks():
        if b.tool not in IAC_RESOURCES:
            continue
        name = ir.catalog[b.tool].name
        if b.tool in CLUSTER_TOOLS:
            instances = cluster_instances(ir, b.tool)
            if len(instances) > 1:
                ir.notes.append(f"{name} : {len(instances)} clusters distincts (un par nom d'environnement), "
                                "décrits dans la même pile.")
            for i, (sfx, params) in enumerate(instances):
                res = _resource(ir, b.tool, params, sfx, first=(i == 0))
                label = f"{name} ({sfx[1:]})" if sfx else name
                main_parts.append(f"# --- {label}\n{res}")
            ir.cover(b.tool)
            continue
        res = _resource(ir, b.tool)
        if res:
            main_parts.append(f"# --- {name}\n{res}")
            if b.tool not in COMMENT_ONLY:
                ir.cover(b.tool)
    main_parts += db_blocks
    ir.cover(*(p.id for p in ir.providers))
    if ir.iac and ir.iac.id in ("terraform", "opentofu"):
        ir.cover(ir.iac.id)
    variables = [f"# {HEADER}"]
    if ir.has("eks"):
        variables += ['variable "vpc_id" {\n  type        = string\n  description = "VPC du cluster EKS"\n}',
                      'variable "subnet_ids" {\n  type        = list(string)\n  description = "Sous-réseaux privés du cluster"\n}']
    if ir.has("gcp"):
        pid = ir.params("gcp").get("project_id", "mon-projet")
        variables.append(f'variable "gcp_project_id" {{\n  type    = string\n  default = "{pid}"\n}}')
    if ir.has("ovhcloud"):
        variables.append('variable "ovh_service_name" {\n  type        = string\n  description = "Identifiant du projet Public Cloud OVHcloud"\n}')
    variables += db_variables
    files = {
        f"{DIR}/versions.tf": versions,
        f"{DIR}/main.tf": "\n\n".join(x for x in main_parts if x) + "\n",
        f"{DIR}/variables.tf": "\n\n".join(variables) + "\n",
    }
    if db_outputs:
        files[f"{DIR}/outputs.tf"] = "\n\n".join([f"# {HEADER}", *db_outputs]) + "\n"
    return files
