# SPDX-License-Identifier: Apache-2.0
"""Utilitaires partagés par les générateurs."""

from __future__ import annotations

import yaml

from ..ir import IR

HEADER = "Généré par DevOps Builder — à relire avant usage."


class _PyDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):  # noqa: ARG002 — pas d'ancres YAML : toutes les CI ne les lisent pas
        return True


# Émetteur C de libyaml quand PyYAML en dispose : même texte, cinq à dix fois plus rapide (le contrôle R31
# rend tous les fichiers à chaque modification du projet)
_Base = getattr(yaml, "CSafeDumper", None) if yaml.__with_libyaml__ else None


class _Dumper(_Base or yaml.SafeDumper):  # type: ignore[misc]
    def ignore_aliases(self, data):  # noqa: ARG002
        return True


def _str_presenter(dumper: yaml.SafeDumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_presenter)
_PyDumper.add_representer(str, _str_presenter)


class _IndentedDumper(_PyDumper):
    """Listes indentées sous leur clé, comme l'attendent yamllint et ansible-lint."""

    def increase_indent(self, flow=False, indentless=False):  # noqa: ARG002
        return super().increase_indent(flow, False)


def dump_yaml(data, comment: str | None = HEADER, indent_lists: bool = False) -> str:
    dumper = _IndentedDumper if indent_lists else _Dumper
    text = yaml.dump(data, Dumper=dumper, sort_keys=False, allow_unicode=True, width=200)
    head = f"# {comment}\n" if comment else ""
    return head + text


def dump_yaml_docs(docs: list, comment: str | None = HEADER) -> str:
    parts = [yaml.dump(d, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=200) for d in docs]
    head = f"# {comment}\n" if comment else ""
    return head + "---\n".join(parts)


AUDIENCES = {
    "aws": "sts.amazonaws.com",
    "gcp": "https://iam.googleapis.com/$GCP_WORKLOAD_IDENTITY_PROVIDER",
    "azure": "api://AzureADTokenExchange",
}
TOKEN_VARS = {"aws": "AWS_OIDC_TOKEN", "gcp": "GCP_OIDC_TOKEN", "azure": "AZURE_OIDC_TOKEN"}


def cloud_auth_lines(ir: IR, cloud: str, token_var: str | None, infra: bool = False) -> list[str]:
    """Authentification cloud en shell, valable pour la CLI comme pour Terraform.

    `token_var` : variable contenant le jeton OIDC émis par la CI ; None si la
    CI n'en émet pas (repli sur des identifiants statiques). `infra` : job d'infrastructure, qui prend
    l'identité aux droits étendus à la place de celle du déploiement.
    """
    oidc = ir.project.cloud_auth == "oidc" and token_var is not None
    if oidc and infra:
        from ..ir import DEPLOY_IDENTITY, INFRA_IDENTITY
        swap = f'export {DEPLOY_IDENTITY[cloud]}="${INFRA_IDENTITY[cloud][0]}"   # identité des jobs d\'infrastructure'
        return [swap, *cloud_auth_lines(ir, cloud, token_var)]
    if cloud == "aws":
        if oidc:
            return [f'echo "${token_var}" > /tmp/aws_oidc_token',
                    "export AWS_WEB_IDENTITY_TOKEN_FILE=/tmp/aws_oidc_token AWS_ROLE_SESSION_NAME=ci"]
        return ["# Identifiants AWS fournis par AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY"]
    if cloud == "gcp":
        if oidc:
            cred = (
                '{"type":"external_account",'
                '"audience":"//iam.googleapis.com/\'"$GCP_WORKLOAD_IDENTITY_PROVIDER"\'",'
                '"subject_token_type":"urn:ietf:params:oauth:token-type:jwt",'
                '"token_url":"https://sts.googleapis.com/v1/token",'
                '"service_account_impersonation_url":"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/\'"$GCP_SERVICE_ACCOUNT"\':generateAccessToken",'
                '"credential_source":{"file":"/tmp/gcp_oidc_token"}}'
            )
            return [f'echo "${token_var}" > /tmp/gcp_oidc_token',
                    f"echo '{cred}' > /tmp/gcp-cred.json",
                    "export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-cred.json",
                    "if command -v gcloud >/dev/null; then gcloud auth login --cred-file=/tmp/gcp-cred.json --quiet; fi"]
        return ['echo "$GCP_SA_KEY" > /tmp/gcp-key.json',
                "export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-key.json",
                "if command -v gcloud >/dev/null; then gcloud auth activate-service-account --key-file /tmp/gcp-key.json; fi"]
    if cloud == "azure":
        common = 'export ARM_CLIENT_ID="$AZURE_CLIENT_ID" ARM_TENANT_ID="$AZURE_TENANT_ID" ARM_SUBSCRIPTION_ID="$AZURE_SUBSCRIPTION_ID"'
        if oidc:
            return [common, f'export ARM_USE_OIDC=true ARM_OIDC_TOKEN="${token_var}"',
                    f'if command -v az >/dev/null; then az login --service-principal -u "$AZURE_CLIENT_ID" -t "$AZURE_TENANT_ID" --federated-token "${token_var}" >/dev/null; fi']
        return [common, 'export ARM_CLIENT_SECRET="$AZURE_CLIENT_SECRET"',
                'if command -v az >/dev/null; then az login --service-principal -u "$AZURE_CLIENT_ID" -p "$AZURE_CLIENT_SECRET" -t "$AZURE_TENANT_ID" >/dev/null; fi']
    return []


def full_script(ir: IR, step, token_vars: dict[str, str] | None) -> list[str]:
    lines: list[str] = []
    for cloud in step.cloud:
        tv = token_vars.get(cloud) if token_vars else None
        lines += cloud_auth_lines(ir, cloud, tv, infra=step.stage == "infra")
    return lines + list(step.script)


def align_attrs(text: str) -> str:
    """Aligne les « = » des attributs consécutifs d'un même niveau, comme `tofu fmt`."""
    import re
    attr = re.compile(r"^(\s*)([A-Za-z_][\w-]*)(\s*)=\s(.*)$")
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = attr.match(lines[i])
        if not m or m.group(4).rstrip().endswith(("{", "[", "(", "<<-EOT", "<<EOT")):
            out.append(lines[i])
            i += 1
            continue
        run = []
        while i < len(lines):
            m = attr.match(lines[i])
            if not m or (run and m.group(1) != run[0].group(1)):
                break
            if m.group(4).rstrip().endswith(("{", "[", "(", "<<-EOT", "<<EOT")):
                break
            run.append(m)
            i += 1
        width = max(len(r.group(2)) for r in run)
        out += [f"{r.group(1)}{r.group(2).ljust(width)} = {r.group(4)}" for r in run]
    return "\n".join(out)
