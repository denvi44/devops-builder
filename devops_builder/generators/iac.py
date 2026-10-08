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


def _resource(ir: IR, tool_id: str) -> str | None:
    p = ir.params(tool_id)
    app = ir.app
    if tool_id == "eks":
        return f'''module "eks" {{
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
      desired_size   = 2
    }}
  }}
}}'''
    if tool_id == "ecr":
        return f'resource "aws_ecr_repository" "app" {{\n  name                 = "{p.get("repository", app)}"\n  image_tag_mutability = "IMMUTABLE"\n\n  image_scanning_configuration {{\n    scan_on_push = true\n  }}\n}}'
    if tool_id == "aws-secrets-manager":
        return f'resource "aws_secretsmanager_secret" "app" {{\n  name = "{app}"\n}}'
    if tool_id in ("s3", "gcs"):
        return (f"# Le bucket {p.get('bucket')} porte l'état de cette pile : il est créé à part (amorçage),\n"
                "# pas par la pile qui l'utilise.")
    if tool_id == "gke":
        return f'''resource "google_container_cluster" "main" {{
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
        return _azure(ir, tool_id, p)
    if tool_id == "ovh-mks":
        return (f'resource "ovh_cloud_project_kube" "main" {{\n  service_name = var.ovh_service_name\n'
                f'  name         = "{p.get("cluster_name")}"\n  region       = "{p.get("region", "GRA11")}"\n}}')
    if tool_id == "kapsule":
        return f'''resource "scaleway_k8s_cluster" "main" {{
  name                        = "{p.get("cluster_name")}"
  version                     = "1.32"
  cni                         = "cilium"
  delete_additional_resources = false
}}

resource "scaleway_k8s_pool" "default" {{
  cluster_id = scaleway_k8s_cluster.main.id
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


def _azure(ir: IR, tool_id: str, p: dict) -> str:
    app = ir.app
    loc = ir.params("azure").get("location", "francecentral")
    if tool_id == "aks":
        return f'''resource "azurerm_kubernetes_cluster" "main" {{
  name                = "{p.get("cluster_name")}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "{app}"

  default_node_pool {{
    name       = "default"
    node_count = 2
    vm_size    = "Standard_D2s_v5"
  }}

  identity {{
    type = "SystemAssigned"
  }}
}}'''
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


IAC_RESOURCES = {
    "eks", "ecr", "aws-secrets-manager", "s3", "gke", "artifact-registry", "gcr", "gcp-secret-manager",
    "gcs", "aks", "acr", "azure-key-vault", "azure-blob", "azure-container-apps", "ovh-mks", "kapsule",
    "scaleway-registry", "oks",
}


def terraform(ir: IR) -> dict[str, str]:
    if not ir.providers and not any(ir.has(t) for t in IAC_RESOURCES):
        return {}
    required = []
    for p in ir.providers:
        src, ver = PROVIDER_SOURCES.get(p.id, (p.terraform_provider, ">= 0"))
        required.append(f'    {PROVIDER_LOCAL.get(p.id, p.id)} = {{\n      source  = "{src}"\n      version = "{ver}"\n    }}')
    versions = (f"# {HEADER}\nterraform {{\n  required_version = \">= 1.6\"\n\n  required_providers {{\n"
                + "\n".join(required) + "\n  }\n\n" + _backend(ir) + "\n}\n")
    main_parts = [f"# {HEADER}", _providers_block(ir)]
    if ir.has("azure"):
        rg = ir.params("azure").get("resource_group", "rg-mon-projet")
        loc = ir.params("azure").get("location", "francecentral")
        main_parts.append(f'resource "azurerm_resource_group" "main" {{\n  name     = "{rg}"\n  location = "{loc}"\n}}')
    for _, b in ir.project.all_bricks():
        if b.tool in IAC_RESOURCES:
            res = _resource(ir, b.tool)
            if res:
                main_parts.append(f"# --- {ir.catalog[b.tool].name}\n{res}")
    variables = [f"# {HEADER}"]
    if ir.has("eks"):
        variables += ['variable "vpc_id" {\n  type        = string\n  description = "VPC du cluster EKS"\n}',
                      'variable "subnet_ids" {\n  type        = list(string)\n  description = "Sous-réseaux privés du cluster"\n}']
    if ir.has("gcp"):
        pid = ir.params("gcp").get("project_id", "mon-projet")
        variables.append(f'variable "gcp_project_id" {{\n  type    = string\n  default = "{pid}"\n}}')
    if ir.has("ovhcloud"):
        variables.append('variable "ovh_service_name" {\n  type        = string\n  description = "Identifiant du projet Public Cloud OVHcloud"\n}')
    return {
        f"{DIR}/versions.tf": versions,
        f"{DIR}/main.tf": "\n\n".join(x for x in main_parts if x) + "\n",
        f"{DIR}/variables.tf": "\n\n".join(variables) + "\n",
    }
