# SPDX-License-Identifier: Apache-2.0
"""Clé de chiffrement du projet (capacité « chiffrement (KMS) » de la 1.1) : une clé, utilisée par les ressources.

Une brique par cloud qui en propose une (aws-kms, gcp-kms, azure-kms, scaleway-key-manager) ; Outscale n'en a pas dans
le catalogue et le KMS d'OVHcloud (OKMS) se commande hors de la pile. La clé tourne seule (rotation). Chez AWS, elle
chiffre les disques des machines, Amazon RDS, ElastiCache, SQS et les secrets écrits dans Secrets Manager ; chez les
autres clouds, la pile crée la clé et la donne en sortie (le rattachement aux disques et aux services demande des
droits propres à chaque cloud, une note le dit).
"""

from __future__ import annotations

import re

from ..ir import IR
from .common import align_attrs

KMS = {"aws-kms": "aws", "gcp-kms": "gcp", "azure-kms": "azure", "scaleway-key-manager": "scaleway"}
AWS_KEY = "aws_kms_key.main.arn"


def tool(ir: IR) -> str | None:
    return next((t for t in KMS if ir.has(t)), None)


def aws_key(ir: IR) -> str | None:
    """Référence de la clé AWS du projet, ou None sans brique aws-kms."""
    return AWS_KEY if ir.has("aws-kms") else None


def _key_name(ir: IR, p: dict) -> str:
    return str(p.get("key") or ir.app)


def _aws(ir, p):
    name = _key_name(ir, p)
    res = align_attrs(f'''resource "aws_kms_key" "main" {{
  description             = "Clé de chiffrement de {ir.app}"
  enable_key_rotation     = true
  deletion_window_in_days = {int(p.get("deletion_days") or 30)}
}}

resource "aws_kms_alias" "main" {{
  name          = "alias/{name}"
  target_key_id = aws_kms_key.main.key_id
}}''')
    return [res], ['output "kms_key_arn" {\n  description = "Clé de chiffrement du projet"\n  value       = aws_kms_key.main.arn\n}']


def _gcp(ir, p):
    region = ir.params("gcp").get("region", "europe-west9")
    name = _key_name(ir, p)
    res = align_attrs(f'''resource "google_kms_key_ring" "main" {{
  name     = "{name}"
  location = "{region}"
}}

resource "google_kms_crypto_key" "main" {{
  name            = "{name}"
  key_ring        = google_kms_key_ring.main.id
  rotation_period = "7776000s"

  lifecycle {{
    prevent_destroy = true
  }}
}}''')
    return [res], ['output "kms_key_id" {\n  description = "Clé de chiffrement du projet"\n  value       = google_kms_crypto_key.main.id\n}']


def _azure(ir, p):
    name = _key_name(ir, p)
    vault = str(p.get("vault_name") or f"kv-{ir.app}-keys")
    client = "" if ir.has("azure-key-vault") else 'data "azurerm_client_config" "current" {}\n\n'
    res = align_attrs(f'''{client}resource "azurerm_key_vault" "kms" {{
  name                       = "{vault}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
}}

resource "azurerm_role_assignment" "kms_officer" {{
  scope                = azurerm_key_vault.kms.id
  role_definition_name = "Key Vault Crypto Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}}

resource "azurerm_key_vault_key" "main" {{
  name         = "{name}"
  key_vault_id = azurerm_key_vault.kms.id
  key_type     = "RSA"
  key_size     = 2048
  key_opts     = ["decrypt", "encrypt", "unwrapKey", "wrapKey"]

  rotation_policy {{
    automatic {{
      time_before_expiry = "P30D"
    }}

    expire_after         = "P1Y"
    notify_before_expiry = "P29D"
  }}

  depends_on = [azurerm_role_assignment.kms_officer]
}}''')
    return [res], ['output "kms_key_id" {\n  description = "Clé de chiffrement du projet (Key Vault)"\n  value       = azurerm_key_vault_key.main.id\n}']


def _scaleway(ir, p):
    name = _key_name(ir, p)
    res = align_attrs(f'''resource "scaleway_key_manager_key" "main" {{
  name        = "{name}"
  description = "Clé de chiffrement de {ir.app}"
  usage       = "symmetric_encryption"
  algorithm   = "aes_256_gcm"
  unprotected = false
  rotation_policy {{
    rotation_period = "720h"
  }}
}}''')
    return [res], ['output "kms_key_id" {\n  description = "Clé de chiffrement du projet"\n  value       = scaleway_key_manager_key.main.id\n}']


RENDER = {"aws-kms": _aws, "gcp-kms": _gcp, "azure-kms": _azure, "scaleway-key-manager": _scaleway}


def terraform_blocks(ir: IR) -> tuple[list[str], list[str]]:
    tid = tool(ir)
    if tid is None:
        return [], []
    ir.cover(tid)
    name = ir.catalog[tid].name
    blocks, outs = RENDER[tid](ir, ir.params(tid))
    if tid == "aws-kms":
        used = ["les disques des machines" if _hosts(ir) else "", "Amazon RDS" if ir.has("aws-rds") else "",
                "ElastiCache" if ir.has("aws-elasticache") else "", "Amazon SQS" if ir.has("aws-sqs") else "",
                "les secrets de Secrets Manager" if ir.has("aws-secrets-manager") else ""]
        used = [u for u in used if u]
        ir.notes.append(f"{name} : une clé à rotation automatique" + (f", utilisée pour {', '.join(used)}." if used else
                        " ; aucune ressource chiffrable du projet ne l'utilise encore."))
        ir.notes.append("Amazon KMS : les rôles IAM de l'application doivent pouvoir utiliser la clé (kms:Decrypt, "
                        "kms:GenerateDataKey) pour lire une file SQS ou un secret chiffrés par elle. L'état OpenTofu "
                        "(bucket S3 créé hors de la pile) se chiffre avec `kms_key_id` dans le bloc backend.")
    else:
        ir.notes.append(f"{name} : la pile crée la clé (rotation automatique) et la donne en sortie ; le rattachement "
                        "aux disques, bases et secrets demande des droits propres à ce cloud et reste à faire.")
    return [f"# --- {name}\n" + "\n\n".join(blocks)], outs


def _hosts(ir: IR) -> bool:
    from .hosts import creates_hosts
    return ir.has("aws-ec2") and creates_hosts(ir)


def vault_name_ok(name: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z][a-zA-Z0-9-]{1,22}[a-zA-Z0-9]", name))
