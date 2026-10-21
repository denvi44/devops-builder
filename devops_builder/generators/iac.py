# SPDX-License-Identifier: Apache-2.0
"""Génération Terraform / OpenTofu : fournisseurs, backend d'état et services managés."""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import IR
from . import dns, lb, network
from .common import HEADER, align_attrs

DIR = "infra/terraform"

# Versions majeures vérifiées le 2026-10-11 (azurerm 5.0, sorti en juillet 2026, change des schémas :
# la pile reste en 4.x tant que la migration n'est pas validée).
PROVIDER_SOURCES = {
    "aws": ("hashicorp/aws", "~> 6.0"),
    "gcp": ("hashicorp/google", "~> 7.0"),
    "azure": ("hashicorp/azurerm", "~> 4.0"),
    "ovhcloud": ("ovh/ovh", "~> 2.0"),
    "outscale": ("outscale/outscale", "~> 1.0"),
    "scaleway": ("scaleway/scaleway", "~> 2.0"),
}
PROVIDER_LOCAL = {"aws": "aws", "gcp": "google", "azure": "azurerm", "ovhcloud": "ovh",
                  "outscale": "outscale", "scaleway": "scaleway"}
REQUIRED_VERSION = ">= 1.10"  # verrou d'état natif du backend S3 (use_lockfile)


@dataclass
class TfVar:
    """Variable de la pile sans valeur connue : variable CI TF_VAR_<nom>, exemple et valeur factice (Floci)."""

    name: str
    type: str
    description: str
    example: str
    dummy: str


TF_VARS = {
    "vpc_id": TfVar("vpc_id", "string", "VPC du cluster EKS", '"vpc-0123456789abcdef0"', '"vpc-0f10c1"'),
    "subnet_ids": TfVar("subnet_ids", "list(string)", "Sous-réseaux privés du cluster",
                        '["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"]', '["subnet-0f10c1a", "subnet-0f10c1b"]'),
    "db_subnet_group": TfVar("db_subnet_group", "string", "Groupe de sous-réseaux privés des instances RDS",
                             '"rds-prive"', '"floci"'),
    "ssh_public_key": TfVar("ssh_public_key", "string",
                            "Clé SSH publique du compte de déploiement (moitié publique de SSH_PRIVATE_KEY)",
                            '"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA… deploy@ci"',
                            '"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFlociFlociFlociFlociFlociFlociFlociFloci floci"'),
    "db_security_group_ids": TfVar("db_security_group_ids", "list(string)",
                                   "Groupes de sécurité autorisant l'application à joindre la base",
                                   '["sg-0123456789abcdef0"]', '["sg-0f10c1"]'),
}

# Backends compatibles S3 hors AWS : point d'accès et variables CI qui donnent les clés S3
# Stockages S3 compatibles qui acceptent l'écriture conditionnelle (If-None-Match) : le verrou natif du backend
# s3 (use_lockfile, Terraform et OpenTofu 1.10+) y fonctionne. Outscale OOS ne la documente pas.
S3_LOCKFILE = ("scaleway-object-storage", "ovh-object-storage")
S3_COMPATIBLE = {
    "scaleway-object-storage": ("https://s3.{region}.scw.cloud", "SCW_ACCESS_KEY", "SCW_SECRET_KEY"),
    "ovh-object-storage": ("https://s3.{region}.io.cloud.ovh.net", "OVH_S3_ACCESS_KEY", "OVH_S3_SECRET_KEY"),
    "outscale-oos": ("https://oos.{region}.outscale.com", "OSC_ACCESS_KEY", "OSC_SECRET_KEY"),
}
REMOTE_BACKENDS = ("s3", "gcs", "azure-blob", *S3_COMPATIBLE)


def backend_tool(ir: IR) -> str | None:
    """Brique qui porte l'état de la pile, ou None (état local)."""
    return next((t for t in REMOTE_BACKENDS if ir.has(t)), None)


def s3_compatible_region(ir: IR, tool_id: str) -> str:
    if tool_id == "scaleway-object-storage":
        return str(ir.params("scaleway").get("region", "fr-par"))
    if tool_id == "outscale-oos":
        return str(ir.params("outscale").get("region", "eu-west-2"))
    return str(ir.params(tool_id).get("region", "gra"))


def backend_credentials(ir: IR) -> list[str]:
    """Lignes shell qui donnent au backend S3 compatible les clés du fournisseur."""
    tool = backend_tool(ir)
    if tool not in S3_COMPATIBLE:
        return []
    _, key, secret = S3_COMPATIBLE[tool]
    if tool == "ovh-object-storage":
        ir.add_var(key, "Clé d'accès S3 OVHcloud (utilisateur Public Cloud), pour l'état Terraform")
        ir.add_var(secret, "Clé secrète S3 OVHcloud, pour l'état Terraform")
    return [f'export AWS_ACCESS_KEY_ID="${key}" AWS_SECRET_ACCESS_KEY="${secret}"']


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
        return (f'  backend "s3" {{\n    bucket       = "{b.get("bucket")}"\n    key          = "{ir.app}/terraform.tfstate"\n'
                f'    region       = "{region}"\n    encrypt      = true\n    use_lockfile = true\n  }}')
    tool = backend_tool(ir)
    if tool in S3_COMPATIBLE:
        region = s3_compatible_region(ir, tool)
        endpoint = S3_COMPATIBLE[tool][0].format(region=region)
        name = ir.catalog[tool].name
        lock = tool in S3_LOCKFILE
        return (f'  # {name} : clés S3 dans AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (posées par la CI).\n'
                + ("  # Verrou d'état : fichier .tflock créé par écriture conditionnelle (If-None-Match).\n" if lock else
                   "  # Pas de verrou d'état (écriture conditionnelle non documentée) : la CI sérialise les apply ;\n"
                   "  # ne pas lancer d'apply depuis un poste pendant qu'un job tourne.\n")
                + f'  backend "s3" {{\n    bucket                      = "{ir.params(tool).get("bucket")}"\n'
                f'    key                         = "{ir.app}/terraform.tfstate"\n'
                f'    region                      = "{region}"\n'
                f'    endpoints                   = {{ s3 = "{endpoint}" }}\n'
                f'    skip_credentials_validation = true\n    skip_region_validation      = true\n'
                f'    skip_requesting_account_id  = true\n    skip_metadata_api_check     = true\n'
                f'    skip_s3_checksum            = true\n'
                + ('    use_lockfile                = true\n' if lock else '') + '  }')
    if ir.has("gcs"):
        b = ir.params("gcs")
        return f'  backend "gcs" {{\n    bucket = "{b.get("bucket")}"\n    prefix = "{ir.app}"\n  }}'
    if ir.has("azure-blob"):
        b = ir.params("azure-blob")
        rg = ir.params("azure").get("resource_group", "rg-mon-projet")
        return (f'  backend "azurerm" {{\n    resource_group_name  = "{rg}"\n'
                f'    storage_account_name = "{b.get("storage_account")}"\n    container_name       = "{b.get("container")}"\n'
                f'    key                  = "{ir.app}.tfstate"\n  }}')
    return "  # Backend local : ajouter un stockage objet du fournisseur pour partager l'état entre les jobs (R44)."


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


def _pn(tool_id: str, line: str, ir: IR) -> str:
    """Ligne d'argument qui rattache une ressource au réseau privé, quand la brique est dans le projet."""
    return f"\n  {line}" if network.present(ir, tool_id) else ""


def _gke_network(ir: IR) -> str:
    if not network.present(ir, "gcp-vpc"):
        return ""
    return ("\n\n  network    = google_compute_network.main.id\n  subnetwork = google_compute_subnetwork.main.id\n\n"
            "  ip_allocation_policy {}")


def _ovh_mks_network(ir: IR) -> str:
    if not network.present(ir, "ovh-private-network"):
        return ""
    return (f"\n  private_network_id = {network.OVH_NETWORK_ID}\n"
            "  nodes_subnet_id    = ovh_cloud_project_network_private_subnet.main.id\n\n"
            "  depends_on = [ovh_cloud_project_network_private_subnet.main]")


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
  version = "~> 21.0"

  name               = "{p.get("cluster_name")}"
  kubernetes_version = "{p.get("version", "1.36")}"
  vpc_id             = {"aws_vpc.main.id" if network.present(ir) else "var.vpc_id"}
  subnet_ids         = {"aws_subnet.private[*].id" if network.present(ir) else "var.subnet_ids"}

  # accès Kubernetes : l'identité qui applique la pile, le rôle de déploiement de la CI et les personnes
  # déclarées dans cluster_admin_arns (l'identité qui applique change après le premier apply depuis le poste)
  enable_cluster_creator_admin_permissions = true
  access_entries = {{
    for name, arn in merge({{ ci = var.ci_deploy_role_arn }}, {{ for i, a in var.cluster_admin_arns : "admin-${{i}}" => a }}) :
    name => {{
      principal_arn = arn
      policy_associations = {{
        admin = {{
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {{ type = "cluster" }}
        }}
      }}
    }} if arn != ""
  }}

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
    if tool_id in ("aws-secrets-manager", "gcp-secret-manager") and _secrets_written(ir):
        return None  # un secret par base et par environnement, plus bas
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
  deletion_protection = true{_gke_network(ir)}
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
        return align_attrs(f'resource "ovh_cloud_project_kube" "main{sfx}" {{\n  service_name = var.ovh_service_name\n'
                f'  name         = "{p.get("cluster_name")}"\n  region       = "{p.get("region", "GRA11")}"{_ovh_mks_network(ir)}\n}}')
    if tool_id == "kapsule":
        latest = ('data "scaleway_k8s_version" "latest" {\n  name = "latest"\n}\n\n' if first else "")
        return latest + f'''resource "scaleway_k8s_cluster" "main{sfx}" {{
  name                        = "{p.get("cluster_name")}"
  version                     = data.scaleway_k8s_version.latest.name
  cni                         = "cilium"
  delete_additional_resources = false{_pn("scaleway-vpc", "private_network_id          = scaleway_vpc_private_network.main.id", ir)}
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


def _secrets_written(ir: IR) -> bool:
    from . import data, secrets
    return bool(secrets.tf_dbs(ir, data.compose_dbs(ir)))


def _kv_rbac(ir: IR) -> bool:
    """Key Vault en mode RBAC : la pile y écrit, ou y donne la lecture à External Secrets."""
    from . import secrets
    return _secrets_written(ir) or secrets.eso_identity(ir) == "azure-key-vault"


def _aks_workload_identity(ir: IR) -> str:
    from . import secrets
    if secrets.eso_identity(ir) != "azure-key-vault":
        return ""
    return "\n\n  oidc_issuer_enabled       = true\n  workload_identity_enabled = true"


def _azure(ir: IR, tool_id: str, p: dict, sfx: str = "", first: bool = True) -> str:
    app = ir.app
    loc = ir.params("azure").get("location", "francecentral")
    if tool_id == "aks":
        oms = workspace = ""
        aks_subnet = aks_profile = ""
        if network.present(ir, "azure-vnet"):
            aks_subnet = "\n    vnet_subnet_id = azurerm_subnet.aks.id"
            aks_profile = ('\n\n  network_profile {\n    network_plugin = "azure"\n    service_cidr   = "172.31.0.0/16"\n'
                          '    dns_service_ip = "172.31.0.10"\n  }')
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
        return align_attrs(f'''resource "azurerm_kubernetes_cluster" "main{sfx}" {{
  name                = "{p.get("cluster_name")}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "{dns}"

  default_node_pool {{
    name       = "default"
    node_count = 2
    vm_size    = "Standard_D2s_v5"{aks_subnet}
  }}

  identity {{
    type = "SystemAssigned"
  }}{aks_profile}{oms}{_aks_workload_identity(ir)}
}}{workspace}''')
    if tool_id == "acr":
        return (f'resource "azurerm_container_registry" "main" {{\n  name                = "{p.get("registry_name", "monappregistry")}"\n'
                f'  resource_group_name = azurerm_resource_group.main.name\n  location            = azurerm_resource_group.main.location\n'
                f'  sku                 = "Standard"\n}}')
    if tool_id == "azure-key-vault":
        rbac = "\n  enable_rbac_authorization = true" if _kv_rbac(ir) else ""
        pad = "      " if rbac else ""
        return (f'data "azurerm_client_config" "current" {{}}\n\nresource "azurerm_key_vault" "main" {{\n'
                f'  name                {pad}= "{p.get("vault_name", "kv-" + app)}"\n  location            {pad}= azurerm_resource_group.main.location\n'
                f'  resource_group_name {pad}= azurerm_resource_group.main.name\n'
                f'  tenant_id           {pad}= data.azurerm_client_config.current.tenant_id\n  sku_name            {pad}= "standard"{rbac}\n}}')
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
    "scaleway-registry", "oks", *network.NETWORK, *lb.LB, *dns.DNS,
}


def terraform(ir: IR) -> dict[str, str]:
    from . import data
    if not ir.providers and not any(ir.has(t) for t in IAC_RESOURCES):
        return {}
    from . import hosts
    db_blocks, _db_variables, db_outputs = data.terraform_blocks(ir)
    host_blocks, host_outputs = hosts.terraform_blocks(ir)
    from . import secrets
    secret_blocks, secret_random = secrets.terraform_blocks(ir, data.compose_dbs(ir))
    eso_blocks, eso_outputs = secrets.eso_identity_blocks(ir)
    backup_blocks, backup_outputs = data.backup_terraform_blocks(ir)
    eso_blocks = data.pod_identity_addons(ir) + eso_blocks + backup_blocks
    eso_outputs = eso_outputs + backup_outputs
    required = []
    for p in ir.providers:
        src, ver = PROVIDER_SOURCES.get(p.id, (p.terraform_provider, ">= 0"))
        required.append(f'    {PROVIDER_LOCAL.get(p.id, p.id)} = {{\n      source  = "{src}"\n      version = "{ver}"\n    }}')
    if data.needs_random(ir) or secret_random:
        required.append('    random = {\n      source  = "hashicorp/random"\n      version = "~> 3.6"\n    }')
    versions = (f"# {HEADER}\nterraform {{\n  required_version = \"{REQUIRED_VERSION}\"\n\n  required_providers {{\n"
                + "\n".join(required) + "\n  }\n\n" + _backend(ir) + "\n}\n")
    main_parts = [f"# {HEADER}", _providers_block(ir)]
    if ir.has("azure"):
        rg = ir.params("azure").get("resource_group", "rg-mon-projet")
        loc = ir.params("azure").get("location", "francecentral")
        main_parts.append(f'resource "azurerm_resource_group" "main" {{\n  name     = "{rg}"\n  location = "{loc}"\n}}')
    for _, b in ir.project.all_bricks():
        if b.tool not in IAC_RESOURCES or b.tool in network.NETWORK or b.tool in lb.LB or b.tool in dns.DNS:
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
    net_blocks, net_outputs = network.terraform_blocks(ir)
    network.host_note(ir)
    lb_blocks, lb_outputs = lb.terraform_blocks(ir)
    dns_blocks, dns_outputs = dns.terraform_blocks(ir)
    main_parts += network.default_data_blocks(ir) + net_blocks + host_blocks + lb_blocks + dns_blocks + db_blocks + secret_blocks + eso_blocks
    ir.cover(*(p.id for p in ir.providers))
    if backend_tool(ir) in S3_COMPATIBLE:
        ir.cover(backend_tool(ir))  # porte l'état : écrit dans le bloc backend de versions.tf
    if ir.iac and ir.iac.id in ("terraform", "opentofu"):
        ir.cover(ir.iac.id)
    variables = [f"# {HEADER}"]
    for tv in required_vars(ir):
        variables.append(f'variable "{tv.name}" {{\n  type        = {tv.type}\n  description = "{tv.description}"\n}}')
    if ir.has("eks"):
        arn = ir.params("aws").get("role_arn") or ""
        variables.append('variable "ci_deploy_role_arn" {\n  type        = string\n'
                         '  description = "Rôle de déploiement de la CI (AWS_ROLE_ARN), autorisé sur le cluster ; '
                         'vide = aucun"\n'
                         f'  default     = "{arn}"\n}}')
        variables.append('variable "cluster_admin_arns" {\n  type        = list(string)\n'
                         '  description = "Rôles ou utilisateurs IAM des personnes qui administrent le cluster"\n'
                         '  default     = []\n}')
    if ir.has("gcp"):
        pid = ir.params("gcp").get("project_id", "mon-projet")
        variables.append(f'variable "gcp_project_id" {{\n  type    = string\n  default = "{pid}"\n}}')
    if ir.has("ovhcloud"):
        sid = ir.params("ovhcloud").get("service_name", "<id-projet-public-cloud>")
        variables.append('variable "ovh_service_name" {\n  type        = string\n'
                         f'  description = "Identifiant du projet Public Cloud OVHcloud"\n  default     = "{sid}"\n}}')
    files = {
        f"{DIR}/versions.tf": versions,
        f"{DIR}/main.tf": "\n\n".join(x for x in main_parts if x) + "\n",
        f"{DIR}/variables.tf": "\n\n".join(variables) + "\n",
        f"{DIR}/.gitignore": GITIGNORE,
    }
    outputs = _outputs(ir) + net_outputs + host_outputs + lb_outputs + dns_outputs + db_outputs + eso_outputs
    if outputs:
        files[f"{DIR}/outputs.tf"] = "\n\n".join([f"# {HEADER}", *outputs]) + "\n"
    tvs = required_vars(ir)
    if tvs:
        files[f"{DIR}/terraform.tfvars.example"] = (
            f"# {HEADER}\n# Valeurs des variables sans défaut : copier en terraform.tfvars (non versionné) pour un\n"
            "# usage local ; la CI les reçoit par les variables TF_VAR_<nom> (voir PIPELINE.md).\n"
            + "".join(f"{tv.name} = {tv.example}\n" for tv in tvs))
    if ir.has("tflint"):
        files[f"{DIR}/.tflint.hcl"] = TFLINT_CONFIG
        ir.cover("tflint")
    return files


GITIGNORE = """# Généré par DevOps Builder — à relire avant usage.
# État, plans et fichiers locaux : jamais dans Git. Le .terraform.lock.hcl, lui, se versionne.
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
crash.log
crash.*.log
terraform.tfvars
*.auto.tfvars
override.tf
*_override.tf
"""

TFLINT_CONFIG = """# Généré par DevOps Builder — à relire avant usage.
# Règles de base du langage ; ajouter le jeu de règles du cloud (tflint-ruleset-aws, -google, -azurerm)
# avec une version épinglée pour vérifier types d'instance, régions et arguments propres au fournisseur.
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}
"""


def required_vars(ir: IR) -> list[TfVar]:
    """Variables de la pile sans valeur connue, dans l'ordre d'écriture."""
    from .hosts import creates_hosts
    names: list[str] = []
    if creates_hosts(ir):
        names.append("ssh_public_key")
    if network.present(ir, "aws-vpc"):   # le réseau est créé par la pile : plus rien à saisir
        return [TF_VARS[n] for n in names]
    if ir.has("eks"):
        names += ["vpc_id", "subnet_ids"]
    from .data import managed_dbs
    if any(d.id == "aws-rds" for d in managed_dbs(ir)):
        names += ["db_subnet_group", "db_security_group_ids"]
    return [TF_VARS[n] for n in names]


def _outputs(ir: IR) -> list[str]:
    """Sorties utiles après apply : point d'accès des clusters et adresse des registres."""
    out: list[str] = []
    for tool_id in CLUSTER_TOOLS:
        if not ir.has(tool_id):
            continue
        for sfx, _ in cluster_instances(ir, tool_id):
            label = "cluster" + sfx
            if tool_id == "eks":
                out.append(f'output "{label}_name" {{\n  value = module.eks{sfx}.cluster_name\n}}')
                out.append(f'output "{label}_endpoint" {{\n  value = module.eks{sfx}.cluster_endpoint\n}}')
            elif tool_id == "gke":
                out.append(f'output "{label}_name" {{\n  value = google_container_cluster.main{sfx}.name\n}}')
            elif tool_id == "aks":
                out.append(f'output "{label}_name" {{\n  value = azurerm_kubernetes_cluster.main{sfx}.name\n}}')
            elif tool_id == "kapsule":
                out.append(f'output "{label}_apiserver_url" {{\n  value = scaleway_k8s_cluster.main{sfx}.apiserver_url\n}}')
            elif tool_id == "ovh-mks":
                out.append(f'output "{label}_id" {{\n  value = ovh_cloud_project_kube.main{sfx}.id\n}}')
    registries = {"ecr": "aws_ecr_repository.app.repository_url",
                  "artifact-registry": "google_artifact_registry_repository.app.id",
                  "gcr": "google_artifact_registry_repository.app.id",
                  "acr": "azurerm_container_registry.main.login_server",
                  "scaleway-registry": "scaleway_registry_namespace.app.endpoint"}
    for tool_id, expr in registries.items():
        if ir.has(tool_id):
            out.append(f'output "registry" {{\n  value = {expr}\n}}')
            break
    return out
