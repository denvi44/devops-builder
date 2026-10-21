# SPDX-License-Identifier: Apache-2.0
"""File de messages du projet (capacité « file de messages » de la 1.1) : une file par environnement.

Une brique par cloud qui en propose une (aws-sqs, gcp-pubsub, azure-service-bus, scaleway-queues, ovh-kafka) ;
Outscale n'en a pas. La production porte le nom choisi dans la brique, les autres environnements ce nom suffixé.
L'adresse de chaque file sort de la pile (`queue_<environnement>_url`) : c'est elle que l'application reçoit.
"""

from __future__ import annotations

from ..ir import IR
from .common import align_attrs

QUEUE = {"aws-sqs": "aws", "gcp-pubsub": "gcp", "azure-service-bus": "azure", "scaleway-queues": "scaleway",
         "ovh-kafka": "ovhcloud"}


def tool(ir: IR) -> str | None:
    return next((t for t in QUEUE if ir.has(t)), None)


def env_names(ir: IR, p: dict, key: str = "queue", prefix: str = "queue") -> list[tuple[str, str, object]]:
    """(étiquette, nom, environnement) : un par nom d'environnement distinct ; la production porte le nom de la brique."""
    base = str(p.get(key) or ir.app)
    out, seen = [], set()
    for env in ir.envs:
        name = base if env.kind == "production" else f"{base}-{env.id}"
        if name in seen:
            continue
        seen.add(name)
        out.append((prefix + "_" + env.id.replace("-", "_") if ir.multi_env else prefix, name, env))
    return out


def _items(ir: IR, p: dict) -> list[tuple[str, str, object]]:
    return env_names(ir, p)


def _out(label: str, desc: str, value: str, sensitive: bool = False) -> str:
    rows = [("description", f'"{desc}"'), ("value", value)] + ([("sensitive", "true")] if sensitive else [])
    return f'output "{label}" {{\n' + align_attrs("\n".join(f"  {k} = {v}" for k, v in rows)) + "\n}"


def _aws(ir, p, days):
    blocks, outs = [], []
    sse = "kms_master_key_id         = aws_kms_key.main.arn" if ir.has("aws-kms") else "sqs_managed_sse_enabled   = true"
    for label, name, _ in _items(ir, p):
        blocks.append(align_attrs(f'''resource "aws_sqs_queue" "{label}_dlq" {{
  name                      = "{name}-dlq"
  message_retention_seconds = 1209600
  {sse}
}}

resource "aws_sqs_queue" "{label}" {{
  name                      = "{name}"
  message_retention_seconds = {days * 86400}
  {sse}
  redrive_policy = jsonencode({{
    deadLetterTargetArn = aws_sqs_queue.{label}_dlq.arn
    maxReceiveCount     = 5
  }})
}}'''))
        outs.append(_out(f"{label}_url", "Adresse de la file SQS", f"aws_sqs_queue.{label}.url"))
    return blocks, outs


def _gcp(ir, p, days):
    blocks, outs = [], []
    for label, name, _ in _items(ir, p):
        blocks.append(align_attrs(f'''resource "google_pubsub_topic" "{label}" {{
  name = "{name}"
}}

resource "google_pubsub_subscription" "{label}" {{
  name                       = "{name}-sub"
  topic                      = google_pubsub_topic.{label}.id
  ack_deadline_seconds       = 30
  message_retention_duration = "{days * 86400}s"
}}'''))
        outs.append(_out(f"{label}_url", "Sujet Pub/Sub (projects/<projet>/topics/<nom>)",
                         f"google_pubsub_topic.{label}.id"))
        outs.append(_out(f"{label}_subscription", "Abonnement Pub/Sub", f"google_pubsub_subscription.{label}.id"))
    return blocks, outs


def _azure(ir, p, days):
    ns = str(p.get("namespace") or f"{ir.app}-bus")
    blocks = [align_attrs(f'''resource "azurerm_servicebus_namespace" "main" {{
  name                = "{ns}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"
}}''')]
    outs = []
    for label, name, _ in _items(ir, p):
        blocks.append(align_attrs(f'''resource "azurerm_servicebus_queue" "{label}" {{
  name                                 = "{name}"
  namespace_id                         = azurerm_servicebus_namespace.main.id
  default_message_ttl                  = "P{days}D"
  max_delivery_count                   = 5
  dead_lettering_on_message_expiration = true
}}'''))
        outs.append(_out(f"{label}_url", "Espace de noms Service Bus et nom de la file",
                         f'"${{azurerm_servicebus_namespace.main.name}}.servicebus.windows.net/${{azurerm_servicebus_queue.{label}.name}}"'))
    return blocks, outs


def _scaleway(ir, p, days):
    blocks = ['resource "scaleway_mnq_sqs" "main" {\n}']
    outs = []
    for label, name, _ in _items(ir, p):
        blocks.append(align_attrs(f'''resource "scaleway_mnq_sqs_credentials" "{label}" {{
  project_id = scaleway_mnq_sqs.main.project_id
  name       = "{name}-app"

  permissions {{
    can_publish = true
    can_receive = true
    can_manage  = false
  }}
}}

resource "scaleway_mnq_sqs_queue" "{label}" {{
  project_id      = scaleway_mnq_sqs.main.project_id
  name            = "{name}"
  sqs_endpoint    = scaleway_mnq_sqs.main.endpoint
  access_key      = scaleway_mnq_sqs_credentials.{label}.access_key
  secret_key      = scaleway_mnq_sqs_credentials.{label}.secret_key
  message_max_age = {days * 86400}
}}'''))
        outs.append(_out(f"{label}_url", "Adresse de la file", f"scaleway_mnq_sqs_queue.{label}.url"))
        outs.append(_out(f"{label}_access_key", "Identifiant d'accès de l'application",
                         f"scaleway_mnq_sqs_credentials.{label}.access_key", sensitive=True))
        outs.append(_out(f"{label}_secret_key", "Clé secrète de l'application",
                         f"scaleway_mnq_sqs_credentials.{label}.secret_key", sensitive=True))
    return blocks, outs


def _ovh(ir, p, days):
    region = str(p.get("region") or "GRA")
    nodes = "\n".join(f'  nodes {{\n    region = "{region}"\n  }}\n' for _ in range(3)).rstrip("\n")
    blocks = [f'''resource "ovh_cloud_project_database" "kafka" {{
  service_name = var.ovh_service_name
  description  = "{ir.app}-kafka"
  engine       = "kafka"
  version      = "3.8"
  plan         = "essential"
  flavor       = "db1-4"

{nodes}
}}''']
    outs = [_out("kafka_endpoints", "Adresses du cluster Kafka", "ovh_cloud_project_database.kafka.endpoints")]
    for label, name, _ in _items(ir, p):
        blocks.append(align_attrs(f'''resource "ovh_cloud_project_database_kafka_topic" "{label}" {{
  service_name = ovh_cloud_project_database.kafka.service_name
  cluster_id   = ovh_cloud_project_database.kafka.id
  name         = "{name}"
  partitions   = 3
  replication  = 3
  retention_hours = {p_days_hours(p)}
}}'''))
        outs.append(_out(f"{label}_url", "Sujet Kafka", f"ovh_cloud_project_database_kafka_topic.{label}.name"))
    return blocks, outs


def p_days_hours(p: dict) -> int:
    return _days(p) * 24


def _days(p: dict) -> int:
    return max(1, min(7, int(p.get("retention_days") or 4)))


RENDER = {"aws-sqs": _aws, "gcp-pubsub": _gcp, "azure-service-bus": _azure, "scaleway-queues": _scaleway,
          "ovh-kafka": _ovh}


def terraform_blocks(ir: IR) -> tuple[list[str], list[str]]:
    tid = tool(ir)
    if tid is None:
        return [], []
    ir.cover(tid)
    name = ir.catalog[tid].name
    p = ir.params(tid)
    blocks, outs = RENDER[tid](ir, p, _days(p))
    names = ", ".join(n for _, n, _ in _items(ir, p))
    ir.notes.append(f"{name} : {'un sujet' if tid in ('ovh-kafka', 'gcp-pubsub') else 'une file'} par environnement "
                    f"({names}) ; l'adresse de chacune sort de la pile (queue_<environnement>_url) : la donner à "
                    "l'application (variable QUEUE_URL).")
    if tid == "aws-sqs":
        ir.notes.append("Amazon SQS : l'application a besoin d'un rôle IAM autorisant sqs:SendMessage, "
                        "sqs:ReceiveMessage et sqs:DeleteMessage sur la file ; chaque file a sa file des messages morts "
                        "(5 réceptions).")
    elif tid == "scaleway-queues":
        ir.notes.append("Scaleway Queues : l'identifiant et la clé secrète de l'application sortent de la pile en sortie sensible "
                        "(queue_<environnement>_access_key et _secret_key) ; les ranger dans les secrets avant de la donner à l'application.")
    elif tid == "ovh-kafka":
        ir.notes.append("OVHcloud Kafka : créer l'utilisateur et ses droits (ACL) et autoriser les adresses de "
                        "l'application dans la console ou par OpenTofu.")
    return [f"# --- {name}\n" + "\n\n".join(blocks)], outs
