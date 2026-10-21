# SPDX-License-Identifier: Apache-2.0
"""Fonctions serverless du projet (capacité « fonctions serverless » de la 1.1) : une fonction par environnement.

Une brique par cloud qui en propose (aws-lambda, gcp-functions, azure-functions, scaleway-functions) ; OVHcloud n'a pas
encore d'offre et Outscale n'en a pas. La pile crée la fonction avec un code de remplacement (qu'elle ne réécrit plus
ensuite) et son déclencheur HTTP public ; la CI déploie le vrai code (`deploy_script`). La production porte le nom
choisi dans la brique, les autres environnements ce nom suffixé.
"""

from __future__ import annotations

import re

from ..ir import IR
from .common import align_attrs
from .queue import env_names

FUNCTIONS = {"aws-lambda": "aws", "gcp-functions": "gcp", "azure-functions": "azure", "scaleway-functions": "scaleway"}
ARCHIVE = ("aws-lambda", "gcp-functions")   # le code de remplacement est un zip fabriqué par la pile


def tool(ir: IR) -> str | None:
    return next((t for t in FUNCTIONS if ir.has(t)), None)


def needs_archive(ir: IR) -> bool:
    return any(ir.has(t) for t in ARCHIVE)


def names(ir: IR) -> list[tuple[str, str, object]]:
    tid = tool(ir)
    return env_names(ir, ir.params(tid), "function", "fn") if tid else []


def function_name(ir: IR, env) -> str | None:
    return next((n for _, n, e in names(ir) if e.id == env.id), None) or next((n for _, n, _ in names(ir)), None)


def _out(label: str, desc: str, value: str) -> str:
    return f'output "{label}" {{\n  description = "{desc}"\n  value       = {value}\n}}'


def _family(runtime: str) -> str:
    return "python" if runtime.lower().startswith("python") else "node" if re.match(r"(nodejs|node)", runtime.lower()) else "autre"


def _placeholder(p: dict, google: bool = False) -> tuple[list[tuple[str, str]], bool]:
    """Fichiers du code de remplacement (nom, contenu) et si le runtime est pris en charge."""
    rt = str(p.get("runtime") or "")
    handler = str(p.get("handler") or "main.handler")
    module = handler.split(".")[0] or "main"
    fam = _family(rt)
    if fam == "python" and google:
        return [("main.py", "import functions_framework\\n\\n\\n@functions_framework.http\\ndef " + handler.split(".")[-1]
                 + '(request):\\n    return "Code à déployer par la CI"\\n'),
                ("requirements.txt", "functions-framework==3.*\\n")], True
    if fam == "python":
        return [(f"{module}.py", "def " + handler.split(".")[-1]
                 + '(event, context):\\n    return {"statusCode": 200, "body": "Code à déployer par la CI"}\\n')], True
    if fam == "node":
        fn = handler.split(".")[-1]
        return [(f"{module}.js", "exports." + fn + ' = async () => ({ statusCode: 200, body: "Code à déployer par la CI" });\\n')], True
    return [("LISEZMOI.txt", "Code à déployer par la CI\\n")], False


def _archive(files: list[tuple[str, str]]) -> str:
    esc = lambda c: c.replace('"', '\\"')  # noqa: E731
    srcs = "\n".join(f'  source {{\n    content  = "{esc(c)}"\n    filename = "{n}"\n  }}\n' for n, c in files)
    return (f'data "archive_file" "function_placeholder" {{\n  type        = "zip"\n'
            f'  output_path = "${{path.module}}/function-placeholder.zip"\n\n{srcs.rstrip()}\n}}')


def _aws(ir, p):
    files, _ = _placeholder(p)
    blocks = [_archive(files), align_attrs('''resource "aws_iam_role" "function" {
  name = "@APP@-function"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "function_logs" {
  role       = aws_iam_role.function.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}''').replace("@APP@", ir.app)]
    outs = []
    for label, name, _ in names(ir):
        blocks.append(align_attrs(f'''resource "aws_lambda_function" "{label}" {{
  function_name    = "{name}"
  role             = aws_iam_role.function.arn
  runtime          = "{p.get("runtime", "python3.13")}"
  handler          = "{p.get("handler", "main.handler")}"
  memory_size      = {int(p.get("memory_mb") or 256)}
  timeout          = {int(p.get("timeout_s") or 30)}
  filename         = data.archive_file.function_placeholder.output_path
  source_code_hash = data.archive_file.function_placeholder.output_base64sha256

  # le code est déployé par la CI : la pile ne le réécrit pas
  lifecycle {{
    ignore_changes = [filename, source_code_hash]
  }}
}}

resource "aws_lambda_function_url" "{label}" {{
  function_name      = aws_lambda_function.{label}.function_name
  authorization_type = "NONE"
}}

resource "aws_lambda_permission" "{label}_url" {{
  statement_id           = "AllowPublicUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.{label}.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}}

resource "aws_lambda_permission" "{label}_invoke" {{
  statement_id             = "AllowPublicInvoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.{label}.function_name
  principal                = "*"
  invoked_via_function_url = true
}}'''))
        outs.append(_out(f"{label}_url", "Adresse HTTPS de la fonction", f"aws_lambda_function_url.{label}.function_url"))
    return blocks, outs


def _gcp(ir, p):
    files, _ = _placeholder(p, google=True)
    region = ir.params("gcp").get("region", "europe-west9")
    blocks = [_archive(files), align_attrs(f'''resource "google_storage_bucket" "function_source" {{
  name                        = "${{var.gcp_project_id}}-{ir.app}-fn-src"
  location                    = "{region}"
  uniform_bucket_level_access = true
}}

resource "google_storage_bucket_object" "function_placeholder" {{
  name   = "placeholder-${{data.archive_file.function_placeholder.output_md5}}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_placeholder.output_path
}}''')]
    outs = []
    for label, name, _ in names(ir):
        blocks.append(align_attrs(f'''resource "google_cloudfunctions2_function" "{label}" {{
  name     = "{name}"
  location = "{region}"

  build_config {{
    runtime     = "{p.get("runtime", "python313")}"
    entry_point = "{p.get("handler", "handler")}"
    source {{
      storage_source {{
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_placeholder.name
      }}
    }}
  }}

  service_config {{
    available_memory = "{int(p.get("memory_mb") or 256)}M"
    timeout_seconds  = {int(p.get("timeout_s") or 30)}
  }}

  # le code est déployé par la CI : la pile ne le réécrit pas
  lifecycle {{
    ignore_changes = [build_config[0].source]
  }}
}}

resource "google_cloud_run_service_iam_member" "{label}_public" {{
  location = google_cloudfunctions2_function.{label}.location
  service  = google_cloudfunctions2_function.{label}.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}}'''))
        outs.append(_out(f"{label}_url", "Adresse HTTPS de la fonction",
                         f"google_cloudfunctions2_function.{label}.service_config[0].uri"))
    return blocks, outs


def _azure(ir, p):
    fam, _, ver = str(p.get("runtime") or "python:3.13").partition(":")
    stack = {"python": "python_version", "node": "node_version", "dotnet": "dotnet_version",
             "java": "java_version"}.get(fam, "python_version")
    storage = re.sub(r"[^a-z0-9]", "", ir.app.lower())[:21] + "fn"
    blocks = [align_attrs(f'''resource "azurerm_storage_account" "functions" {{
  name                     = "{storage}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}}

resource "azurerm_service_plan" "functions" {{
  name                = "{ir.app}-functions"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "Y1"
}}''')]
    outs = []
    for label, name, _ in names(ir):
        blocks.append(align_attrs(f'''resource "azurerm_linux_function_app" "{label}" {{
  name                       = "{name}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  service_plan_id            = azurerm_service_plan.functions.id
  storage_account_name       = azurerm_storage_account.functions.name
  storage_account_access_key = azurerm_storage_account.functions.primary_access_key
  https_only                 = true

  site_config {{
    application_stack {{
      {stack} = "{ver}"
    }}
  }}
}}'''))
        outs.append(_out(f"{label}_url", "Adresse HTTPS de l'application de fonctions",
                         f'"https://${{azurerm_linux_function_app.{label}.default_hostname}}"'))
    return blocks, outs


def _scaleway(ir, p):
    blocks = [f'resource "scaleway_function_namespace" "main" {{\n  name = "{ir.app}"\n}}']
    outs = []
    for label, name, _ in names(ir):
        blocks.append(align_attrs(f'''resource "scaleway_function" "{label}" {{
  namespace_id = scaleway_function_namespace.main.id
  name         = "{name}"
  runtime      = "{p.get("runtime", "python313")}"
  handler      = "{p.get("handler", "handler.handle")}"
  privacy      = "public"
  memory_limit = {int(p.get("memory_mb") or 256)}
  timeout      = {int(p.get("timeout_s") or 30)}
}}'''))
        outs.append(_out(f"{label}_url", "Adresse HTTPS de la fonction", f'"https://${{scaleway_function.{label}.domain_name}}"'))
    return blocks, outs


RENDER = {"aws-lambda": _aws, "gcp-functions": _gcp, "azure-functions": _azure, "scaleway-functions": _scaleway}


def terraform_blocks(ir: IR) -> tuple[list[str], list[str]]:
    tid = tool(ir)
    if tid is None:
        return [], []
    ir.cover(tid)
    name = ir.catalog[tid].name
    p = ir.params(tid)
    blocks, outs = RENDER[tid](ir, p)
    listed = ", ".join(n for _, n, _ in names(ir))
    ir.notes.append(f"{name} : une fonction par environnement ({listed}) avec une adresse HTTPS publique en sortie "
                    "(fn_<environnement>_url).")
    if tid in ARCHIVE or tid == "azure-functions":
        ir.notes.append(f"{name} : la pile crée la fonction et ne réécrit plus son code ; la CI déploie le code de "
                        "l'application (étape « Déploiement de la fonction »).")
    if tid in ARCHIVE and not _placeholder(p, google=tid == "gcp-functions")[1]:
        ir.notes.append(f"{name} : le code de remplacement n'existe que pour Python et Node.js ; avec ce runtime, "
                        "la première publication de code est à faire à la main.")
    if tid == "scaleway-functions":
        ir.notes.append("Scaleway Serverless Functions : la fonction est créée sans code ; publier le zip du code avec "
                        "l'outil de Scaleway (scw), la CI générée ne le déploie pas.")
    if tid == "azure-functions":
        ir.notes.append("Azure Functions : le nom de l'application de fonctions et celui du compte de stockage doivent "
                        "être uniques dans tout Azure.")
    return [f"# --- {name}\n" + "\n\n".join(blocks)], outs


def deploy_script(ir: IR, env) -> tuple[str, list[str], str] | None:
    """(image, commandes, nuage) de l'étape CI qui publie le code de la fonction de cet environnement."""
    tid = tool(ir)
    name = function_name(ir, env) if tid else None
    if not tid or not name:
        return None
    p = ir.params(tid, env)
    if tid == "aws-lambda":
        return ("amazon/aws-cli:latest", ["yum install -y zip", "zip -qr function.zip . -x '.git/*'",
                                          f"aws lambda update-function-code --function-name {name} "
                                          "--zip-file fileb://function.zip"], "aws")
    if tid == "gcp-functions":
        g = ir.params("gcp", env)
        return ("google/cloud-sdk:slim", [f'gcloud functions deploy {name} --gen2 --source . --trigger-http '
                                          f'--runtime {p.get("runtime", "python313")} '
                                          f'--entry-point {p.get("handler", "handler")} '
                                          f'--region {g.get("region", "europe-west9")} '
                                          f'--project {g.get("project_id", "mon-projet")}'], "gcp")
    if tid == "azure-functions":
        a = ir.params("azure", env)
        return ("mcr.microsoft.com/azure-cli:latest", ["python3 -m zipfile -c function.zip *",
                                                       f"az functionapp deployment source config-zip --name {name} "
                                                       f"--resource-group {a.get('resource_group', 'rg-mon-projet')} "
                                                       "--src function.zip"], "azure")
    return None
