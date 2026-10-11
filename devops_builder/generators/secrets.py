"""Secrets de l'application : d'où viennent les valeurs, et comment elles atteignent les conteneurs.

Trois sources, une seule convention de nommage :

* **CI** (par défaut) : une variable CI secrète par valeur et par environnement ;
* **SOPS + age** : les valeurs vivent chiffrées dans le dépôt (deploy/secrets/<env>.enc.env) ; la CI
  n'a plus qu'une clé, SOPS_AGE_KEY ;
* **Vault / OpenBao** : les valeurs vivent dans le coffre, sous <mount>/<espace de noms>/<brique> ;
  la CI s'y connecte par JWT (jeton OIDC de GitLab ou GitHub) ou, à défaut, par VAULT_TOKEN.

Sur Kubernetes, External Secrets Operator lit le coffre (Vault, OpenBao ou celui du cloud) et écrit
lui-même les Secrets que l'application attend : la CI ne touche plus aux mots de passe.
"""

from __future__ import annotations

import shlex

from ..databases import Database
from ..ir import IR
from .common import HEADER, dump_yaml

VAULTS = ("vault", "openbao")
CLOUD_STORES = {"aws-secrets-manager": "aws", "gcp-secret-manager": "gcp", "azure-key-vault": "azure"}
STORES = (*VAULTS, *CLOUD_STORES)
SOPS_VERSION = "3.11.0"
FETCH_SCRIPT = "scripts/secrets-fetch.sh"
SEED_SCRIPT = "scripts/secrets-seed.sh"
VAULT_SETUP = "scripts/vault-setup.sh"
SOPS_CONFIG = ".sops.yaml"
STORE_FILE = "platform/external-secrets/cluster-secret-store.yaml"
SOPS_INSTALL = [  # dans $HOME : conteneur root comme machine du runner
    'mkdir -p "$HOME/.local/bin" && export PATH="$HOME/.local/bin:$PATH"',
    f'curl -fsSLo "$HOME/.local/bin/sops" "https://github.com/getsops/sops/releases/download/v{SOPS_VERSION}/'
    f'sops-v{SOPS_VERSION}.linux.amd64"',
    'chmod +x "$HOME/.local/bin/sops"',
]


# ------------------------------------------------------------------ choix
def store(ir: IR) -> str | None:
    """Coffre du pipeline : Vault ou OpenBao d'abord, sinon celui du cloud."""
    return next((t for t in STORES if ir.has(t)), None)


def vault_tool(ir: IR) -> str | None:
    return next((t for t in VAULTS if ir.has(t)), None)


def source(ir: IR) -> str:
    """Source des valeurs pour la CI : sops, vault ou ci."""
    if ir.has("sops"):
        return "sops"
    if vault_tool(ir):
        return "vault"
    return "ci"


def eso(ir: IR) -> bool:
    """External Secrets écrit les Secrets Kubernetes à partir du coffre."""
    return ir.has("external-secrets") and store(ir) is not None


def remote_key(ir: IR, env, tool_id: str) -> str:
    """Clé du secret dans le coffre ; les coffres des clouds n'acceptent pas « / » dans un nom."""
    ns = ir.namespace(env)
    return f"{ns}-{tool_id}" if store(ir) in ("gcp-secret-manager", "azure-key-vault") else f"{ns}/{tool_id}"


def vault_params(ir: IR) -> dict:
    tool = vault_tool(ir)
    return ir.params(tool) if tool else {}


def kv_mount(ir: IR) -> str:
    return str(vault_params(ir).get("kv_mount") or "secret")


# ------------------------------------------------------------------ valeurs
def values(ir: IR, dbs: list[Database]) -> list[tuple[str, str, str]]:
    """(variable lue par les scripts, brique, propriété dans le coffre) des secrets de l'application."""
    out = []
    for db in dbs:
        if db.mode == "self-hosted":
            out.append((db.password_var, db.id, "password"))
        elif db.mode == "managed":
            out.append((db.url_ci_var, db.id, "url"))
    return out


def tools_line(image: str) -> str:
    """curl, bash et jq selon la distribution de l'image du job."""
    if "aws-cli" in image:
        return "yum install -y -q jq >/dev/null"
    if "cloud-sdk" in image:
        return "apt-get update -qq && apt-get install -y -qq jq >/dev/null"
    if "azure-cli" in image:
        return "command -v jq >/dev/null || tdnf install -y -q jq"
    return "apk add --no-cache curl bash jq"


def ci_lines(ir: IR, env, dbs: list[Database], image: str = "alpine") -> list[str]:
    """Lignes de la CI qui chargent les secrets de l'environnement dans des variables du job."""
    src = source(ir)
    if src == "ci" or not values(ir, dbs):
        return []
    # deux lignes : l'affectation échoue avec le script (eval "$(…)" masquerait l'erreur)
    fetch = [f'SECRETS_ENV="$(bash {FETCH_SCRIPT} {env.id})"', 'eval "$SECRETS_ENV"']
    if src == "sops":
        ir.add_var("SOPS_AGE_KEY", "Clé privée age qui déchiffre deploy/secrets/*.enc.env (age-keygen)")
        return [tools_line(image), *SOPS_INSTALL, *fetch]
    addr = str(vault_params(ir).get("address") or "")
    ir.add_var("VAULT_ADDR", f"Adresse de {ir.catalog[vault_tool(ir)].name} joignable depuis la CI", secret=False,
               value=addr)
    ir.add_var("VAULT_TOKEN", "Facultatif : jeton du coffre, si la connexion par JWT de la CI n'est pas configurée")
    return [tools_line(image), *fetch]


def gitlab_id_tokens(ir: IR) -> dict[str, dict]:
    """Jeton OIDC que GitLab remet au job, échangé contre un jeton du coffre."""
    if source(ir) != "vault":
        return {}
    return {"VAULT_ID_TOKEN": {"aud": "$VAULT_ADDR"}}


def origin(ir: IR, db: Database, kube: bool) -> str | None:
    """Où vit la valeur de la base, pour le rapport ; None : variable CI."""
    if db.mode == "operator":
        return None
    key = remote_key(ir, ir.envs[0], db.id).replace(ir.namespace(ir.envs[0]), "<espace de noms>", 1)
    by_tf = bool(tf_dbs(ir, [db]))
    if kube and eso(ir):
        by = ", écrit par Terraform" if by_tf else ""
        return f"{ir.catalog[store(ir)].name}, clé `{key}` (External Secrets{by})"
    if by_tf:
        return f"{ir.catalog[store(ir)].name}, clé `{key}` (écrit par Terraform)"
    if source(ir) == "sops":
        return "`deploy/secrets/<env>.enc.env` (SOPS)"
    if source(ir) == "vault":
        return f"{ir.catalog[vault_tool(ir)].name}, `{kv_mount(ir)}/<espace de noms>/{db.id}`"
    return None


# ------------------------------------------------------------------ scripts
_FETCH = r"""#!/usr/bin/env bash
# @HEADER@
# Charge les secrets d'un environnement (source : @SOURCE@) et les affiche en « export NOM=valeur » :
#   eval "$(bash scripts/secrets-fetch.sh <environnement>)"
# Environnements : @ENVS@. Rien n'est écrit sur le disque.
set -euo pipefail
ENV_ID="${1:?environnement attendu (@ENVS@)}"
case "$ENV_ID" in
@CASES@
  *) echo "Environnement inconnu : $ENV_ID" >&2; exit 2 ;;
esac
@BODY@
"""

_FETCH_SOPS = r"""command -v sops >/dev/null || { echo "Outil manquant : sops" >&2; exit 3; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="$ROOT/deploy/secrets/$ENV_ID.enc.env"
[ -f "$FILE" ] || { echo "Fichier absent : $FILE (scripts/secrets-seed.sh $ENV_ID le crée)" >&2; exit 1; }
sops decrypt --input-type dotenv --output-type dotenv "$FILE" | while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  printf 'export %s=%q\n' "${line%%=*}" "${line#*=}"
done
"""

_FETCH_VAULT = r"""command -v jq >/dev/null || { echo "Outil manquant : jq" >&2; exit 3; }
: "${VAULT_ADDR:?VAULT_ADDR manquant}"
TOKEN="${VAULT_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  JWT="${VAULT_ID_TOKEN:-}"
  if [ -z "$JWT" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then  # GitHub Actions, permission id-token: write
    JWT="$(curl -fsS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
      "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=$VAULT_ADDR" | jq -r .value)"
  fi
  [ -n "$JWT" ] || { echo "Ni VAULT_TOKEN ni jeton OIDC de la CI : connexion au coffre impossible" >&2; exit 1; }
  TOKEN="$(curl -fsS -X POST -d "$(jq -n --arg r "@ROLE@" --arg j "$JWT" '{role: $r, jwt: $j}')" \
    "$VAULT_ADDR/v1/auth/@JWT_MOUNT@/login" | jq -er .auth.client_token)" \
    || { echo "Connexion refusée par le coffre (auth/@JWT_MOUNT@, rôle @ROLE@)" >&2; exit 1; }
fi
read_secret() {  # read_secret VARIABLE CHEMIN PROPRIÉTÉ
  local value
  value="$(curl -fsS -H "X-Vault-Token: $TOKEN" "$VAULT_ADDR/v1/@MOUNT@/data/$2" | jq -er --arg p "$3" '.data.data[$p]')" \
    || { echo "Secret absent : @MOUNT@/$2 ($3) — scripts/secrets-seed.sh $ENV_ID" >&2; exit 1; }
  printf 'export %s=%q\n' "$1" "$value"
}
@READS@
"""


def _cases(ir: IR, ns: bool = True) -> str:
    if not ns:
        return f"  {'|'.join(e.id for e in ir.envs)}) ;;"
    return "\n".join(f"  {e.id}) NS={shlex.quote(ir.namespace(e))} ;;" for e in ir.envs)


def scripts(ir: IR, dbs: list[Database]) -> dict[str, str]:
    """secrets-fetch.sh (lecture par la CI) et secrets-seed.sh (écriture, une fois par environnement)."""
    vals = values(ir, dbs)
    files: dict[str, str] = {}
    envs = ", ".join(e.id for e in ir.envs)
    src = source(ir)
    if vals and src in ("sops", "vault"):
        if src == "sops":
            body = _FETCH_SOPS
        else:
            p = vault_params(ir)
            reads = "\n".join(f'read_secret {var} "$NS/{tool}" {prop}' for var, tool, prop in vals)
            body = (_FETCH_VAULT.replace("@ROLE@", str(p.get("jwt_role") or f"{ir.app}-ci"))
                    .replace("@JWT_MOUNT@", "jwt").replace("@MOUNT@", kv_mount(ir)).replace("@READS@", reads))
        files[FETCH_SCRIPT] = (_FETCH.replace("@HEADER@", HEADER).replace("@SOURCE@", src).replace("@ENVS@", envs)
                               .replace("@CASES@", _cases(ir, src == "vault")).replace("@BODY@", body))
    target = "sops" if src == "sops" else store(ir)
    managed_by_tf = {d.id for d in tf_dbs(ir, dbs)}
    vals = [v for v in vals if v[1] not in managed_by_tf]
    if target in CLOUD_STORES and not eso(ir):
        target = None  # personne ne lirait ces valeurs : la CI garde ses variables
    if vals and target:
        files[SEED_SCRIPT] = _seed(ir, vals, target, envs)
    return files


def _seed(ir: IR, vals: list[tuple[str, str, str]], target: str, envs: str) -> str:
    from .data import URL_SAFE
    names = sorted({v for v, _, _ in vals})
    where = "deploy/secrets/<env>.enc.env (SOPS)" if target == "sops" else ir.catalog[target].name
    head = [
        "#!/usr/bin/env bash", f"# {HEADER}",
        f"# Écrit les secrets d'un environnement dans {where},",
        "# à partir des variables d'environnement du même nom ; une fois par environnement, puis à chaque rotation :",
        f"#   {' '.join(f'{n}=…' for n in names)} scripts/secrets-seed.sh <environnement>",
        f"# Environnements : {envs}.",
        "set -euo pipefail",
        'ENV_ID="${1:?environnement attendu}"', 'case "$ENV_ID" in', _cases(ir, target != "sops"),
        '  *) echo "Environnement inconnu : $ENV_ID" >&2; exit 2 ;;', "esac",
        *[f': "${{{n}:?variable {n} manquante}}"' for n in names]]
    for var, _, prop in vals:
        if prop == "password":  # le mot de passe entre dans une URL de connexion
            head += [f'case "${var}" in *[!{URL_SAFE}]*)',
                     f'  echo "{var} : caractères autorisés {URL_SAFE}" >&2; exit 1 ;;', "esac"]
    head.append("")
    body: list[str] = []
    by_tool: dict[str, list[tuple[str, str]]] = {}
    for var, tool, prop in vals:
        by_tool.setdefault(tool, []).append((var, prop))
    if target == "sops":
        body += ['cd "$(dirname "${BASH_SOURCE[0]}")/.."  # .sops.yaml à la racine du dépôt',
                 'FILE="deploy/secrets/$ENV_ID.enc.env"', 'mkdir -p deploy/secrets', 'TMP="$(mktemp)"',
                 "trap 'rm -f \"$TMP\"' EXIT", "{",
                 *[f'  printf "%s=%s\\n" {var} "${var}"' for var in names], "} | sops encrypt --input-type dotenv "
                 '--output-type dotenv --filename-override "$FILE" /dev/stdin > "$TMP"',
                 'mv "$TMP" "$FILE"', 'echo "Secrets chiffrés dans $FILE : à committer."']
        return "\n".join(head + body) + "\n"
    for tool, pairs in by_tool.items():
        json = "jq -n " + " ".join(f'--arg {prop} "${var}"' for var, prop in pairs) + " '{" + \
               ", ".join(f"{prop}: ${prop}" for _, prop in pairs) + "}'"
        if target in VAULTS:
            body.append(f'curl -fsS -X POST -H "X-Vault-Token: ${{VAULT_TOKEN:?VAULT_TOKEN manquant}}" '
                        f'-d "$({json} | jq \'{{data: .}}\')" "${{VAULT_ADDR:?VAULT_ADDR manquant}}/v1/{kv_mount(ir)}'
                        f'/data/$NS/{tool}" >/dev/null')
        elif target == "aws-secrets-manager":
            body.append(f'value="$({json})"')
            body.append(f'aws secretsmanager put-secret-value --secret-id "$NS/{tool}" --secret-string "$value" >/dev/null '
                        f'2>&1 || aws secretsmanager create-secret --name "$NS/{tool}" --secret-string "$value" >/dev/null')
        elif target == "gcp-secret-manager":
            body.append(f'gcloud secrets describe "$NS-{tool}" >/dev/null 2>&1 || '
                        f'gcloud secrets create "$NS-{tool}" --replication-policy=automatic >/dev/null')
            body.append(f'{json} | gcloud secrets versions add "$NS-{tool}" --data-file=- >/dev/null')
        else:
            vault = ir.params("azure-key-vault").get("vault_name", "kv-" + ir.app)
            body.append(f'az keyvault secret set --vault-name {vault} --name "$NS-{tool}" --value "$({json})" >/dev/null')
        body.append(f'echo "{tool} : secret écrit pour $ENV_ID"')
    return "\n".join(head + body) + "\n"


def sops_files(ir: IR) -> dict[str, str]:
    if not ir.has("sops"):
        return {}
    recipients = str(ir.params("sops").get("age_recipients") or "age1…")
    config = {"creation_rules": [{"path_regex": r"deploy/secrets/.*\.enc\.env$", "age": recipients}]}
    files = {SOPS_CONFIG: dump_yaml(config)}
    ir.cover("sops")
    return files


# ------------------------------------------------------------------ External Secrets
def cluster_secret_store(ir: IR) -> dict[str, str]:
    """ClusterSecretStore unique, appliqué par platform/install.sh après l'opérateur."""
    if not eso(ir):
        return {}
    st = store(ir)
    sa = {"name": "external-secrets", "namespace": "external-secrets"}
    if st in VAULTS:
        server = str(vault_params(ir).get("address") or "") or f"http://{st}.{st}.svc:8200"
        provider = {"vault": {"server": server, "path": kv_mount(ir), "version": "v2",
                              "auth": {"kubernetes": {"mountPath": "kubernetes", "role": "external-secrets",
                                                      "serviceAccountRef": sa}}}}
    elif st == "aws-secrets-manager":
        provider = {"aws": {"service": "SecretsManager", "region": str(ir.params("aws").get("region", "eu-west-3"))}}
        if eso_identity(ir) != st:  # sans Pod Identity : jeton du compte de service, rôle en annotation (IRSA)
            provider["aws"]["auth"] = {"jwt": {"serviceAccountRef": sa}}
    elif st == "gcp-secret-manager":
        provider = {"gcpsm": {"projectID": str(ir.params("gcp").get("project_id", "mon-projet"))}}
    else:
        vault = ir.params("azure-key-vault").get("vault_name", "kv-" + ir.app)
        provider = {"azurekv": {"vaultUrl": f"https://{vault}.vault.azure.net", "authType": "WorkloadIdentity",
                                "serviceAccountRef": sa}}
    doc = {"apiVersion": "external-secrets.io/v1", "kind": "ClusterSecretStore",
           "metadata": {"name": ir.app}, "spec": {"provider": provider}}
    ir.cover("external-secrets", st)
    return {STORE_FILE: dump_yaml(doc)}


def external_secrets(ir: IR, dbs: list[Database], name_of, ns_key: str, helm: bool) -> list[dict]:
    """ExternalSecret par base : le Secret cible a le nom et les clés que l'application lit déjà.

    name_of(db) : nom du Secret ; ns_key : préfixe de la clé dans le coffre (espace de noms) ;
    helm : les gabarits ESO sont protégés du moteur de Helm.
    """
    out = []
    sep = "-" if store(ir) in ("gcp-secret-manager", "azure-key-vault") else "/"
    for db in dbs:
        if db.mode == "operator":
            continue
        name = name_of(db)
        key = f"{ns_key}{sep}{db.id}"
        if db.mode == "self-hosted":
            pw = '{{ "{{" }} .password {{ "}}" }}' if helm else "{{ .password }}"
            template = {"engineVersion": "v2", "data": {"password": pw, "url": db.url(name, pw)}}
            data = [{"secretKey": "password", "remoteRef": {"key": key, "property": "password"}}]
        else:
            template = None
            data = [{"secretKey": "url", "remoteRef": {"key": key, "property": "url"}}]
        target: dict = {"name": name, "creationPolicy": "Owner"}
        if template:
            target["template"] = template
        out.append({"apiVersion": "external-secrets.io/v1", "kind": "ExternalSecret",
                    "metadata": {"name": name},
                    "spec": {"refreshInterval": "1h", "secretStoreRef": {"kind": "ClusterSecretStore", "name": ir.app},
                             "target": target, "data": data}})
    return out


def eso_helm_template(ir: IR, dbs: list[Database]) -> str | None:
    """Gabarit du chart : un ExternalSecret par base, quand le chart ne crée pas le Secret lui-même."""
    if not eso(ir):
        return None
    kept = [d for d in dbs if d.mode != "operator"]
    docs = external_secrets(ir, kept, lambda d: "{{ .Release.Name }}-" + d.id, "{{ .Release.Namespace }}", True)
    parts = [f"# {HEADER}\n# Secrets lus dans {ir.catalog[store(ir)].name} par External Secrets "
             f"(ClusterSecretStore « {ir.app} »)."]
    for db, doc in zip(kept, docs, strict=True):
        key = db.id.replace("-", "_")
        parts.append(f"{{{{- if not .Values.database.{key}.createSecret }}}}\n---\n"
                     + dump_yaml(doc, None) + "{{- end }}")
    return "\n".join(parts) + "\n"


def notes(ir: IR, dbs: list[Database]) -> None:
    vals = values(ir, dbs)
    src = source(ir) if vals else None
    if src == "sops":
        ir.notes.append("Secrets par SOPS : renseigner la clé publique age dans la brique SOPS (.sops.yaml), puis "
                        f"`{SEED_SCRIPT} <environnement>` chiffre les valeurs dans deploy/secrets/<environnement>.enc.env, "
                        "à committer. La CI les déchiffre avec SOPS_AGE_KEY.")
    elif src == "vault":
        name = ir.catalog[vault_tool(ir)].name
        role = str(vault_params(ir).get("jwt_role") or f"{ir.app}-ci")
        ir.notes.append(f"Secrets dans {name} (moteur KV v2 « {kv_mount(ir)} », clés <espace de noms>/<brique>) : "
                        f"`{SEED_SCRIPT} <environnement>` les écrit. La CI s'y connecte par JWT (rôle « {role} » sur "
                        f"auth/jwt, émetteur GitLab ou GitHub, politique de lecture de {kv_mount(ir)}/data/<espace de "
                        "noms>/*) ou par VAULT_TOKEN.")
    if eso(ir) and (ir.project.target in ("kubernetes", "kubernetes-managed") or ir.cluster is not None):
        st = ir.catalog[store(ir)].name
        if store(ir) in VAULTS:
            extra = f" ; {VAULT_SETUP} configure la connexion Kubernetes et le rôle « external-secrets »"
        elif eso_identity(ir):
            extra = " ; la pile Terraform donne au contrôleur la lecture du coffre (identité de charge de travail)"
        else:
            extra = (" ; donner au compte de service external-secrets/external-secrets la lecture du coffre "
                     "(IRSA, Workload Identity, identité managée)")
        what = ("chaque ExternalSecret recrée le Secret de base de données attendu par l'application"
                if any(d.mode != "operator" for d in dbs) else "les ExternalSecret de l'application s'y réfèrent")
        ir.notes.append(f"External Secrets : le ClusterSecretStore « {ir.app} » ({STORE_FILE}, appliqué par "
                        f"platform/install.sh) lit {st} et {what}{extra}.")


# ------------------------------------------------------------------ Terraform
TF_MANAGED_DBS = {"aws-rds": "aws", "cloud-sql": "gcp", "azure-database": "azure"}


def tf_store(ir: IR) -> str | None:
    """Coffre du cloud que la pile Terraform sait remplir (son fournisseur est configuré)."""
    st = store(ir)
    if st in CLOUD_STORES and CLOUD_STORES[st] in {p.id for p in ir.providers}:
        return st
    return None


def tf_dbs(ir: IR, dbs: list[Database]) -> list[Database]:
    """Bases dont la pile écrit le secret : managées qu'elle crée ; autogérées lues par External Secrets."""
    if not tf_store(ir):
        return []
    providers = {p.id for p in ir.providers}
    out = []
    for db in dbs:
        if db.mode == "managed" and TF_MANAGED_DBS.get(db.id) in providers:
            out.append(db)
        elif db.mode == "self-hosted" and eso(ir):
            out.append(db)
    return out


def _tf_label(ir: IR, db: Database, env) -> str:
    base = "secret_" + db.id.replace("-", "_")
    return base + ("_" + env.id.replace("-", "_") if ir.multi_env else "")


def terraform_blocks(ir: IR, dbs: list[Database]) -> tuple[list[str], bool]:
    """Secrets écrits par la pile dans le coffre du cloud ; renvoie aussi le besoin du provider random."""
    from ..databases import env_params
    from .data import _instances, _password
    st = tf_store(ir)
    chosen = tf_dbs(ir, dbs)
    if not st or not chosen:
        return [], False
    blocks: list[str] = []
    random = False
    if st == "azure-key-vault":
        blocks.append('# --- Azure Key Vault : la pile écrit les secrets (rôle RBAC sur le coffre)\n'
                      'resource "azurerm_role_assignment" "kv_terraform" {\n'
                      '  scope                = azurerm_key_vault.main.id\n'
                      '  role_definition_name = "Key Vault Secrets Officer"\n'
                      '  principal_id         = data.azurerm_client_config.current.object_id\n}')
    for db in chosen:
        instances = {}
        if db.mode == "managed":
            for label, _, p in _instances(ir, db):
                instances[str(p.get("instance"))] = label
        masters: set[str] = set()
        for env in ir.envs:
            label = _tf_label(ir, db, env)
            key = remote_key(ir, env, db.id)
            pre: list[str] = []
            if db.mode == "self-hosted":
                random = True
                pre.append(_password(label))
                value = f"jsonencode({{ password = random_password.{label}.result }})"
            else:
                p = env_params(db, ir.project, env)
                inst = instances[str(p.get("instance"))]
                engine = str(p.get("engine") or "postgres")
                if db.id == "aws-rds":
                    if inst not in masters:
                        masters.add(inst)
                        pre.append(f'data "aws_secretsmanager_secret_version" "{inst}_master" {{\n'
                                   f'  secret_id = aws_db_instance.{inst}.master_user_secret[0].secret_arn\n}}')
                    host = f"${{aws_db_instance.{inst}.address}}"
                    pw = (f'${{urlencode(jsondecode(data.aws_secretsmanager_secret_version.{inst}_master'
                          f'.secret_string)["password"])}}')
                elif db.id == "cloud-sql":
                    host = f"${{google_sql_database_instance.{inst}.first_ip_address}}"
                    pw = f"${{random_password.{inst}.result}}"
                else:
                    server = ("azurerm_postgresql_flexible_server" if engine == "postgres"
                              else "azurerm_mysql_flexible_server")
                    host = f"${{{server}.{inst}.fqdn}}"
                    pw = f"${{random_password.{inst}.result}}"
                url = db.url(host, pw)
                # External Secrets lit une propriété du JSON ; un service serverless monte la valeur brute
                value = f'jsonencode({{ url = "{url}" }})' if eso(ir) else f'"{url}"'
            title = f"# --- Secret {key} ({db.tool.name})"
            if st == "aws-secrets-manager":
                body = (f'  name = "{key}"' if env.kind == "production" else
                        f'  name                    = "{key}"\n  recovery_window_in_days = 0')
                res = (f'resource "aws_secretsmanager_secret" "{label}" {{\n{body}\n}}\n\n'
                       f'resource "aws_secretsmanager_secret_version" "{label}" {{\n'
                       f'  secret_id     = aws_secretsmanager_secret.{label}.id\n  secret_string = {value}\n}}')
            elif st == "gcp-secret-manager":
                res = (f'resource "google_secret_manager_secret" "{label}" {{\n  secret_id = "{key}"\n\n'
                       f'  replication {{\n    auto {{}}\n  }}\n}}\n\n'
                       f'resource "google_secret_manager_secret_version" "{label}" {{\n'
                       f'  secret      = google_secret_manager_secret.{label}.id\n  secret_data = {value}\n}}')
            else:
                ctype = "application/json" if value.startswith("jsonencode") else "text/plain"
                res = (f'resource "azurerm_key_vault_secret" "{label}" {{\n  name         = "{key}"\n'
                       f'  key_vault_id = azurerm_key_vault.main.id\n'
                       f'  content_type = "{ctype}"\n'
                       f'  value        = {value}\n\n'
                       f'  depends_on = [azurerm_role_assignment.kv_terraform]\n}}')
            blocks.append(title + "\n" + "\n\n".join([*pre, res]))
    ir.cover(st)
    return blocks, random


def tf_note(ir: IR, dbs: list[Database]) -> None:
    chosen = tf_dbs(ir, dbs)
    if not chosen:
        return
    st = ir.catalog[tf_store(ir)].name
    names = ", ".join(d.tool.name for d in chosen)
    extra = ""
    if any(d.id == "aws-rds" for d in chosen):
        extra = (" L'URL d'Amazon RDS reprend le mot de passe principal géré par RDS : après une rotation, "
                 "relancer `apply` pour la réécrire.")
    shape = "JSON, lu par External Secrets" if eso(ir) else "l'URL de connexion seule, à monter dans le service"
    ir.notes.append(f"{st} : la pile Terraform y écrit les secrets de connexion ({names} ; clé <espace de noms>"
                    f"{'-' if tf_store(ir) != 'aws-secrets-manager' else '/'}<brique>, {shape}) ; les valeurs "
                    f"passent par l'état, à garder dans un backend chiffré à accès restreint.{extra}")


# ------------------------------------------------------------------ assemblage
def files(ir: IR, dbs: list[Database]) -> dict[str, str]:
    """Scripts, configuration SOPS et ClusterSecretStore ; notes du rapport."""
    out: dict[str, str] = {}
    fetched = any(FETCH_SCRIPT in line for st in ir.steps for line in st.script)
    for path, text in scripts(ir, dbs).items():
        if path != FETCH_SCRIPT or fetched:
            out[path] = text
    out.update(sops_files(ir))
    out.update(setup_script(ir))
    if ir.project.target in ("kubernetes", "kubernetes-managed") or ir.cluster is not None:
        out.update(cluster_secret_store(ir))
    if out.get(FETCH_SCRIPT) or out.get(SEED_SCRIPT) or out.get(STORE_FILE):
        ir.cover(*(t for t in (vault_tool(ir), store(ir)) if t))
    notes(ir, dbs)
    tf_note(ir, dbs)
    return out


# ------------------------------------------------------------------ identité d'External Secrets
ESO_SA = ("external-secrets", "external-secrets")  # espace de noms, compte de service du contrôleur
ESO_CLUSTERS = {"aws-secrets-manager": "eks", "gcp-secret-manager": "gke", "azure-key-vault": "aks"}


def eso_identity(ir: IR) -> str | None:
    """Coffre du cloud dont la pile Terraform donne l'accès au contrôleur External Secrets."""
    st = tf_store(ir)
    if st and eso(ir) and ir.has(ESO_CLUSTERS[st]):
        return st
    return None


def eso_identity_blocks(ir: IR) -> tuple[list[str], list[str]]:
    """Blocs main.tf et sorties : Pod Identity (EKS), Workload Identity (GKE, AKS)."""
    from .iac import cluster_instances
    st = eso_identity(ir)
    if not st:
        return [], []
    ns, sa = ESO_SA
    prefixes = sorted({ir.namespace(e) for e in ir.envs})
    clusters = cluster_instances(ir, ESO_CLUSTERS[st])
    title = "# --- External Secrets : lecture du coffre par le contrôleur"
    if st == "aws-secrets-manager":
        arns = ", ".join(f'"arn:aws:secretsmanager:*:*:secret:{p}/*"' for p in prefixes)
        blocks = [f'''{title} (EKS Pod Identity)
resource "aws_iam_role" "external_secrets" {{
  name = "{ir.app}-external-secrets"
  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect    = "Allow"
      Principal = {{ Service = "pods.eks.amazonaws.com" }}
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }}]
  }})
}}

resource "aws_iam_role_policy" "external_secrets" {{
  name = "lecture-secrets"
  role = aws_iam_role.external_secrets.id
  policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = [{arns}]
    }}]
  }})
}}''']
        for sfx, _ in clusters:
            blocks.append(f'''resource "aws_eks_addon" "pod_identity{sfx}" {{
  cluster_name = module.eks{sfx}.cluster_name
  addon_name   = "eks-pod-identity-agent"
}}

resource "aws_eks_pod_identity_association" "external_secrets{sfx}" {{
  cluster_name    = module.eks{sfx}.cluster_name
  namespace       = "{ns}"
  service_account = "{sa}"
  role_arn        = aws_iam_role.external_secrets.arn
}}''')
        outputs = ['output "eso_role_arn" {\n  description = "Rôle IAM du contrôleur External Secrets (Pod Identity)"\n'
                   '  value       = aws_iam_role.external_secrets.arn\n}']
    elif st == "gcp-secret-manager":
        blocks = [f'''{title} (Workload Identity Federation de GKE)
data "google_project" "current" {{
  project_id = var.gcp_project_id
}}

resource "google_project_iam_member" "external_secrets" {{
  project = var.gcp_project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "principal://iam.googleapis.com/projects/${{data.google_project.current.number}}/locations/global/workloadIdentityPools/${{var.gcp_project_id}}.svc.id.goog/subject/ns/{ns}/sa/{sa}"
}}''']
        outputs = []
    else:
        blocks = [f'''{title} (Workload Identity d'AKS)
resource "azurerm_user_assigned_identity" "external_secrets" {{
  name                = "id-{ir.app}-external-secrets"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}}

resource "azurerm_role_assignment" "kv_external_secrets" {{
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.external_secrets.principal_id
}}''']
        for sfx, _ in clusters:
            blocks.append(f'''resource "azurerm_federated_identity_credential" "external_secrets{sfx}" {{
  name                = "external-secrets{sfx.replace("_", "-")}"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.external_secrets.id
  issuer              = azurerm_kubernetes_cluster.main{sfx}.oidc_issuer_url
  subject             = "system:serviceaccount:{ns}:{sa}"
  audience            = ["api://AzureADTokenExchange"]
}}''')
        outputs = ['output "eso_client_id" {\n  description = "Identité managée du contrôleur External Secrets"\n'
                   '  value       = azurerm_user_assigned_identity.external_secrets.client_id\n}',
                   'output "eso_tenant_id" {\n  value = data.azurerm_client_config.current.tenant_id\n}']
    ir.cover(st, "external-secrets")
    return blocks, outputs


def eso_helm_args(ir: IR) -> tuple[list[str], str]:
    """Lignes à placer avant l'installation d'External Secrets, et options du chart (Azure)."""
    if eso_identity(ir) != "azure-key-vault":
        return [], ""
    out = f'{ir.iac_cmd} -chdir="$(dirname "$0")/../infra/terraform" output -raw'
    lines = [f'ESO_CLIENT_ID="${{ESO_CLIENT_ID:-$({out} eso_client_id)}}"',
             f'ESO_TENANT_ID="${{ESO_TENANT_ID:-$({out} eso_tenant_id)}}"']
    args = (' --set-string "serviceAccount.annotations.azure\\.workload\\.identity/client-id=$ESO_CLIENT_ID"'
            ' --set-string "serviceAccount.annotations.azure\\.workload\\.identity/tenant-id=$ESO_TENANT_ID"'
            ' --set-string "podLabels.azure\\.workload\\.identity/use=true"')
    return lines, args


# ------------------------------------------------------------------ configuration du coffre
JWT_ISSUERS = {"gitlab-ci": ("GitLab", "https://gitlab.com"),
               "github-actions": ("GitHub Actions", "https://token.actions.githubusercontent.com")}

_SETUP = r"""#!/usr/bin/env bash
# @HEADER@
# Configure @NAME@ pour @APP@, sans rien supprimer ; relançable sans risque :
#   moteur KV v2 « @MOUNT@ », politique de lecture @POLICIES@@JWT_DOC@@K8S_DOC@
#
#   VAULT_ADDR=https://… VAULT_TOKEN=<jeton d'administration> @ENVHINT@scripts/vault-setup.sh
#
# Variables : VAULT_ADDR, VAULT_TOKEN (racine au premier passage, puis à révoquer)@VARS_DOC@
set -euo pipefail
command -v jq >/dev/null || { echo "Outil manquant : jq" >&2; exit 3; }
: "${VAULT_ADDR:?VAULT_ADDR manquant}"
: "${VAULT_TOKEN:?VAULT_TOKEN manquant : jeton administrateur}"
@REQUIRED@
api() {  # api MÉTHODE CHEMIN [JSON] : corps de la réponse ; l'erreur du coffre sur la sortie d'erreur
  local out code
  out="$(curl -sS -X "$1" -H "X-Vault-Token: $VAULT_TOKEN" ${3:+-H "Content-Type: application/json" -d "$3"} \
    -w '\n%{http_code}' "$VAULT_ADDR/v1/$2")" || return 1
  code="${out##*$'\n'}"
  out="${out%$'\n'*}"
  if [ "$code" -ge 300 ]; then
    echo "$1 $2 : HTTP $code $out" >&2
    return 1
  fi
  printf '%s' "$out"
}
enabled() {  # enabled sys/mounts|sys/auth CHEMIN : déjà activé ?
  api GET "$1" | jq -e --arg p "$2/" '(.data // .) | has($p)' >/dev/null
}
policy() {  # policy NOM PRÉFIXE… : lecture de <moteur>/data/<préfixe>/*
  local name="$1" rules=""
  shift
  for prefix in "$@"; do
    rules+="path \"@MOUNT@/data/$prefix/*\" { capabilities = [\"read\"] }"$'\n'
  done
  api PUT "sys/policies/acl/$name" "$(jq -n --arg p "$rules" '{policy: $p}')" >/dev/null
  echo "Politique $name : lecture de @MOUNT@/data/<préfixe>/* ($*)"
}

api GET auth/token/lookup-self >/dev/null || { echo "VAULT_TOKEN refusé par $VAULT_ADDR" >&2; exit 1; }
if enabled sys/mounts "@MOUNT@"; then
  echo "Moteur @MOUNT@ déjà activé"
else
  api POST "sys/mounts/@MOUNT@" '{"type": "kv", "options": {"version": "2"}}' >/dev/null
  echo "Moteur KV v2 @MOUNT@ activé"
fi
@BODY@
echo "Configuration terminée. Écrire ensuite les secrets : scripts/secrets-seed.sh <environnement>"
"""

_SETUP_JWT = r"""
# Connexion de la CI (@CI@) : jeton OIDC du job, limité au dépôt @CLAIM_DOC@
policy "@CI_POLICY@" @PREFIXES@
ISSUER="${CI_ISSUER:-@ISSUER@}"
if ! enabled sys/auth jwt; then
  api POST sys/auth/jwt '{"type": "jwt"}' >/dev/null
  echo "Méthode auth/jwt activée"
fi
api POST auth/jwt/config "$(jq -n --arg i "$ISSUER" '{oidc_discovery_url: $i, bound_issuer: $i}')" >/dev/null
api POST auth/jwt/role/@ROLE@ "$(jq -n --arg aud "${CI_AUDIENCE:-$VAULT_ADDR}" --arg repo "$CI_REPO" \
  --arg branch "${CI_BRANCH:-main}" '{
    role_type: "jwt", user_claim: "sub", bound_audiences: [$aud],
    bound_claims_type: "string", bound_claims: @CLAIMS@,
    token_policies: ["@CI_POLICY@"], token_ttl: "15m", token_max_ttl: "30m"}')" >/dev/null
echo "Rôle auth/jwt/role/@ROLE@ : $CI_REPO, branche ${CI_BRANCH:-main}, émetteur $ISSUER"
"""

_SETUP_K8S = r"""
# Connexion d'External Secrets : compte de service @SA_NS@/@SA@ du cluster
policy "@ESO_POLICY@" @PREFIXES@
if ! enabled sys/auth kubernetes; then
  api POST sys/auth/kubernetes '{"type": "kubernetes"}' >/dev/null
  echo "Méthode auth/kubernetes activée"
fi
if [ -n "${KUBE_HOST:-}" ]; then  # coffre hors du cluster : adresse, autorité et jeton de relecture
  : "${KUBE_CA_FILE:?KUBE_CA_FILE manquant : autorité de certification du cluster}"
  config="$(jq -n --arg h "$KUBE_HOST" --rawfile ca "$KUBE_CA_FILE" --arg j "${KUBE_REVIEWER_JWT:-}" \
    '{kubernetes_host: $h, kubernetes_ca_cert: $ca} + (if $j == "" then {} else {token_reviewer_jwt: $j} end)')"
else  # coffre dans le cluster : son propre compte de service relit les jetons
  config='{"kubernetes_host": "https://kubernetes.default.svc"}'
fi
api POST auth/kubernetes/config "$config" >/dev/null \
  || { echo "Coffre hors du cluster ? Renseigner KUBE_HOST et KUBE_CA_FILE (voir l'en-tête)" >&2; exit 1; }
api POST auth/kubernetes/role/external-secrets "$(jq -n '{
    bound_service_account_names: ["@SA@"], bound_service_account_namespaces: ["@SA_NS@"],
    token_policies: ["@ESO_POLICY@"], token_ttl: "1h"}')" >/dev/null
echo "Rôle auth/kubernetes/role/external-secrets : @SA_NS@/@SA@"
"""


def jwt_ci(ir: IR) -> tuple[str, str] | None:
    """(nom de la CI, émetteur par défaut) quand la CI sait présenter un jeton OIDC au coffre."""
    return JWT_ISSUERS.get(ir.ci.id) if ir.ci else None


def setup_script(ir: IR) -> dict[str, str]:
    """scripts/vault-setup.sh : KV v2, politiques, auth/jwt pour la CI, auth/kubernetes pour External Secrets."""
    tool = vault_tool(ir)
    if not tool:
        return {}
    k8s = eso(ir) and store(ir) == tool
    ci_reads = source(ir) == "vault" and any(FETCH_SCRIPT in line for st in ir.steps for line in st.script)
    jwt = jwt_ci(ir) if ci_reads else None
    if not (k8s or ci_reads):
        return {}
    mount = kv_mount(ir)
    prefixes = " ".join(sorted({shlex.quote(ir.namespace(e)) for e in ir.envs}))
    role = str(vault_params(ir).get("jwt_role") or f"{ir.app}-ci")
    ci_policy, eso_policy = f"{ir.app}-ci-read", f"{ir.app}-eso-read"
    policies = " et ".join(p for p, on in ((ci_policy, ci_reads), (eso_policy, k8s)) if on)
    body, var_doc, required = "", "", ""
    jwt_doc = k8s_doc = env_hint = ""
    if ci_reads and jwt:
        gitlab = ir.ci.id == "gitlab-ci"
        claims = ('{project_path: $repo, ref_type: "branch", ref: $branch, ref_protected: "true"}' if gitlab
                  else '{repository: $repo, ref: ("refs/heads/" + $branch)}')
        claim_doc = ("et à la branche protégée" if gitlab else "et à la branche")
        body += (_SETUP_JWT.replace("@CI@", jwt[0]).replace("@ISSUER@", jwt[1]).replace("@CLAIMS@", claims)
                 .replace("@CLAIM_DOC@", claim_doc).replace("@ROLE@", role))
        jwt_doc = f",\n#   connexion JWT de la CI ({jwt[0]}, rôle « {role} »)"
        repo = "groupe/projet" if gitlab else "propriétaire/dépôt"
        var_doc += (f",\n#   CI_REPO ({repo}), CI_BRANCH (main par défaut),"
                    f"\n#   CI_ISSUER ({jwt[1]} par défaut{' ; GitLab autohébergé : son adresse' if gitlab else ''}),"
                    "\n#   CI_AUDIENCE (VAULT_ADDR par défaut : l'audience que la CI demande)")
        required = f': "${{CI_REPO:?CI_REPO manquant ({repo})}}"'
        env_hint = f"CI_REPO={repo} "
    elif ci_reads:
        body += f'\npolicy "{ci_policy}" {prefixes}\n'
        body += (f'echo "{ir.ci.name if ir.ci else "La CI"} ne présente pas de jeton OIDC : créer pour elle un jeton '
                 f'limité, par exemple : curl -H \\"X-Vault-Token: $VAULT_TOKEN\\" -d \'{{\\"policies\\": '
                 f'[\\"{ci_policy}\\"], \\"period\\": \\"720h\\"}}\' $VAULT_ADDR/v1/auth/token/create"\n')
    if k8s:
        body += (_SETUP_K8S.replace("@SA_NS@", ESO_SA[0]).replace("@SA@", ESO_SA[1])
                 .replace("@ESO_POLICY@", eso_policy))
        k8s_doc = ",\n#   connexion Kubernetes d'External Secrets (rôle « external-secrets »)"
        var_doc += (",\n#   KUBE_HOST, KUBE_CA_FILE, KUBE_REVIEWER_JWT : seulement si le coffre tourne hors du "
                    "cluster")
    text = (_SETUP.replace("@HEADER@", HEADER).replace("@NAME@", ir.catalog[tool].name).replace("@APP@", ir.app)
            .replace("@MOUNT@", mount).replace("@POLICIES@", policies).replace("@JWT_DOC@", jwt_doc)
            .replace("@K8S_DOC@", k8s_doc).replace("@VARS_DOC@", var_doc).replace("@ENVHINT@", env_hint)
            .replace("@REQUIRED@", required).replace("@BODY@", body.replace("@MOUNT@", mount)
                                                      .replace("@CI_POLICY@", ci_policy)
                                                      .replace("@PREFIXES@", prefixes)))
    text = text.replace("@PREFIXES@", prefixes)
    return {VAULT_SETUP: text}
