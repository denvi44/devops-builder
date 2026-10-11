"""Bases de données : services Compose, manifestes Kubernetes, Terraform des bases managées.

Le contrat avec l'application est toujours le même : elle lit l'URL de connexion complète
dans DATABASE_URL (relationnel), MONGODB_URI (documents) ou REDIS_URL (clé-valeur), et
la commande de migration éventuelle s'exécute avec son image avant qu'elle ne démarre.
"""

from __future__ import annotations

import copy
import re

from ..databases import (
    HEALTHCHECKS,
    MIGRATIONS,
    PASSWORD_HINT,
    Database,
    databases,
    env_params,
    migration_command,
)
from ..ir import IR
from .common import HEADER, dump_yaml, dump_yaml_docs

SECRETS_SCRIPT = "deploy/secrets.sh"
BACKUP_SCRIPT = "scripts/db-backup.sh"
URL_SAFE = "A-Za-z0-9._~-"
RAW = "__RAW__"


def _raw(expr: str) -> str:
    """Expression Helm à écrire sans guillemets (valeur numérique)."""
    return RAW + expr


def _unraw(text: str) -> str:
    return re.sub(r"'?" + RAW + r"([^'\n]*)'?", r"\1", text)


def _key(db: Database) -> str:
    return db.id.replace("-", "_")


def _var(ir: IR, name: str, env) -> str:
    return ir.env_var(name, env)


# ----------------------------------------------------------------- sélection
def all_dbs(ir: IR) -> list[Database]:
    return databases(ir.project, ir.catalog)


def compose_dbs(ir: IR) -> list[Database]:
    """Bases utilisables avec Compose : autogérées (conteneur) et managées (URL)."""
    return [d for d in all_dbs(ir) if d.mode in ("self-hosted", "managed")]


def kube_dbs(ir: IR) -> list[Database]:
    return all_dbs(ir)


def needs_secrets(ir: IR) -> bool:
    return bool(compose_dbs(ir))


# ----------------------------------------------------------------- variables CI
def secret_bindings(ir: IR, env, dbs: list[Database]) -> list[tuple[str, str]]:
    """(variable lue par les scripts, variable CI) pour un environnement ; déclare les variables CI."""
    out = []
    where = f" ({env.display})" if ir.multi_env else ""
    for db in dbs:
        if db.mode == "self-hosted":
            ci = _var(ir, db.password_var, env)
            ir.add_var(ci, f"Mot de passe {db.tool.name}{where} — {PASSWORD_HINT}")
            out.append((db.password_var, ci))
        elif db.mode == "managed":
            ci = _var(ir, db.url_ci_var, env)
            ir.add_var(ci, f"URL de connexion à {db.tool.name}{where}, lue par l'application dans {db.url_var} ; "
                           "à composer après création de l'instance (sorties Terraform)")
            out.append((db.url_ci_var, ci))
    return out


def env_prefix(bindings: list[tuple[str, str]]) -> str:
    """« VAR="$VAR_ENV" » devant une commande, quand la variable CI porte le suffixe d'environnement."""
    parts = [f'{local}="${ci}"' for local, ci in bindings if local != ci]
    return (" ".join(parts) + " ") if parts else ""


# ----------------------------------------------------------------- Compose
def _compose_service(db: Database) -> dict:
    e = db.engine
    svc: dict = {"image": db.image, "restart": "unless-stopped"}
    env: dict[str, str] = {}
    if e.family in ("sql", "document"):
        env[e.user_env] = db.user
        env[e.db_env] = db.name
        env.update(dict(e.extra_env))
    if env:
        svc["environment"] = env
    svc["env_file"] = [f"secrets/{db.id}.env"]
    if e.family == "key-value":
        binary = "valkey-server" if db.id == "valkey" else "redis-server"
        svc["command"] = ["sh", "-c", f'exec {binary} --requirepass "$${{{db.password_var}}}" --appendonly yes']
    svc["volumes"] = [f"{db.id}-data:{e.data_path(db.version)}"]
    svc["healthcheck"] = {"test": ["CMD-SHELL", HEALTHCHECKS[db.id]], "interval": "10s", "timeout": "5s",
                          "retries": 10, "start_period": "30s"}
    return svc


def compose_parts(ir: IR, app_service: dict, image: str) -> dict[str, dict]:
    """Complète le service de l'application ; renvoie les services à ajouter (migrations, bases)."""
    dbs = compose_dbs(ir)
    if not dbs:
        return {}
    services: dict[str, dict] = {}
    app_service["env_file"] = ["secrets/app.env"]
    depends: dict[str, dict] = {}
    for db in dbs:
        if db.mode == "self-hosted":
            services[db.id] = _compose_service(db)
            depends[db.id] = {"condition": "service_healthy"}
            ir.cover(db.id)
        else:
            ir.cover(db.id)  # l'instance est décrite en Terraform si l'IaC est présente (sinon R31)
    command = migration_command(ir.project, ir.catalog)
    if command:
        migrate: dict = {"image": image, "command": ["sh", "-c", command], "env_file": ["secrets/app.env"],
                         "restart": "no"}
        if depends:
            migrate["depends_on"] = copy.deepcopy(depends)
        services = {"migrate": migrate, **services}
        depends = {"migrate": {"condition": "service_completed_successfully"}, **depends}
        ir.cover(MIGRATIONS)
    if depends:
        app_service["depends_on"] = depends
    return services


def secrets_script(ir: IR) -> dict[str, str]:
    """deploy/secrets.sh : écrit les fichiers lus par Compose (env_file) à partir des variables."""
    dbs = compose_dbs(ir)
    if not dbs:
        return {}
    lines = ["#!/bin/sh", f"# {HEADER}",
             "# Écrit les fichiers de secrets lus par Docker Compose (env_file) à partir des variables",
             "# d'environnement ; appelé par la CI avant chaque déploiement, ou à la main sur un poste :",
             "#   " + " ".join(f"{v}=…" for v in _script_vars(dbs)) + f" sh {SECRETS_SCRIPT} deploy/secrets",
             "set -eu", 'dir="${1:-secrets}"', "umask 077", 'mkdir -p "$dir"', ""]
    for var in _script_vars(dbs):
        lines.append(f': "${{{var}:?variable {var} manquante}}"')
    for db in dbs:
        if db.mode == "self-hosted":
            lines += [f'case "${db.password_var}" in *[!{URL_SAFE}]*)',
                      f'  echo "{db.password_var} : caractères autorisés {URL_SAFE} (le mot de passe entre dans une URL)" >&2',
                      "  exit 1 ;;", "esac"]
    lines.append("")
    app_lines = []
    for db in dbs:
        if db.mode == "self-hosted":
            pw = "$" + db.password_var
            name = db.engine.password_env or db.password_var
            lines += [f'cat > "$dir/{db.id}.env" <<EOF', f"{name}={pw}", "EOF"]
            app_lines.append(f"{db.url_var}={db.url(db.id, pw)}")
        else:
            app_lines.append(f"{db.url_var}=${db.url_ci_var}")
    lines += ['cat > "$dir/app.env" <<EOF', *app_lines, "EOF", 'echo "Secrets écrits dans $dir"', ""]
    return {SECRETS_SCRIPT: "\n".join(lines)}


def _script_vars(dbs: list[Database]) -> list[str]:
    return list(dict.fromkeys(d.password_var if d.mode == "self-hosted" else d.url_ci_var for d in dbs))


DUMPS = {
    "postgresql": ('pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', "dump"),
    "mariadb": ('mariadb-dump -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" --single-transaction "$MARIADB_DATABASE"', "sql"),
    "mysql": ('mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --single-transaction --no-tablespaces "$MYSQL_DATABASE"', "sql"),
    "mongodb": ('mongodump --archive --gzip -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" '
                "--authenticationDatabase admin", "archive.gz"),
}


def backup_script(ir: IR) -> dict[str, str]:
    dbs = [d for d in compose_dbs(ir) if d.mode == "self-hosted" and d.id in DUMPS]
    if not dbs:
        return {}
    lines = ["#!/bin/sh", f"# {HEADER}",
             "# Sauvegarde logique des bases du projet Compose, à planifier sur l'hôte (cron, timer systemd) :",
             f"#   {BACKUP_SCRIPT.split('/')[-1]} /opt/<projet> [/var/backups/<projet>]      KEEP_DAYS=7 par défaut",
             "# Le nom du projet Compose est celui du dossier (docker compose -p).",
             "set -eu", 'dir="${1:?dossier du projet Compose, ex. /opt/mon-app}"',
             'project="$(basename "$dir")"', 'dest="${2:-/var/backups/$project}"', 'keep="${KEEP_DAYS:-7}"',
             'stamp="$(date +%Y%m%d-%H%M%S)"', "umask 077", 'mkdir -p "$dest"',
             'dc() { docker compose --project-directory "$dir" -p "$project" "$@"; }', ""]
    for db in dbs:
        cmd, ext = DUMPS[db.id]
        lines += [f"# {db.tool.name}",
                  f"dc exec -T {db.id} sh -c '{cmd}' > \"$dest/{db.id}-$stamp.{ext}\"",
                  f'echo "{db.tool.name} → $dest/{db.id}-$stamp.{ext}"']
    lines += ["", 'find "$dest" -type f -mtime +"$keep" -delete', ""]
    return {BACKUP_SCRIPT: "\n".join(lines)}


# ----------------------------------------------------------------- Kubernetes
def _health_exec(db: Database) -> list[str]:
    return ["sh", "-c", HEALTHCHECKS[db.id].replace("$$", "$")]


def _db_env(db: Database, secret: str) -> list[dict]:
    e = db.engine
    env: list[dict] = []
    if e.family in ("sql", "document"):
        env += [{"name": e.user_env, "value": db.user}, {"name": e.db_env, "value": db.name}]
        env += [{"name": k, "value": v} for k, v in e.extra_env]
    name = e.password_env or db.password_var
    env.append({"name": name, "valueFrom": {"secretKeyRef": {"name": secret, "key": "password"}}})
    if db.id == "postgresql" and db.engine.data_path(db.version).endswith("/data"):
        env.append({"name": "PGDATA", "value": "/var/lib/postgresql/data/pgdata"})  # le volume contient lost+found
    return env


def statefulset_docs(db: Database, name: str, image: str, storage: str, labels: dict) -> list[dict]:
    e = db.engine
    container: dict = {"name": db.id, "image": image, "ports": [{"containerPort": e.port, "name": db.id[:15]}],
                       "env": _db_env(db, name)}
    if e.family == "key-value":
        binary = "valkey-server" if db.id == "valkey" else "redis-server"
        container["command"] = ["sh", "-c", f'exec {binary} --requirepass "${db.password_var}" --appendonly yes']
    container["readinessProbe"] = {"exec": {"command": _health_exec(db)}, "initialDelaySeconds": 10,
                                   "periodSeconds": 10}
    container["resources"] = {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"memory": "1Gi"}}
    container["volumeMounts"] = [{"name": "data", "mountPath": e.data_path(db.version)}]
    lab = lambda: dict(labels)  # noqa: E731 — une copie par usage, sans ancre YAML
    service = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "labels": lab()},
               "spec": {"selector": lab(), "ports": [{"port": e.port, "targetPort": e.port, "name": db.id[:15]}]}}
    sts = {"apiVersion": "apps/v1", "kind": "StatefulSet", "metadata": {"name": name, "labels": lab()},
           "spec": {"serviceName": name, "replicas": 1, "selector": {"matchLabels": lab()},
                    "template": {"metadata": {"labels": lab()}, "spec": {"containers": [container]}},
                    "volumeClaimTemplates": [{"metadata": {"name": "data"},
                                              "spec": {"accessModes": ["ReadWriteOnce"],
                                                       "resources": {"requests": {"storage": storage}}}}]}}
    return [service, sts]


def cnpg_cluster(db: Database, name: str, instances, storage: str, image: str) -> dict:
    return {"apiVersion": "postgresql.cnpg.io/v1", "kind": "Cluster", "metadata": {"name": name},
            "spec": {"instances": instances, "imageName": image, "storage": {"size": storage},
                     "bootstrap": {"initdb": {"database": db.name, "owner": db.user}}}}


def cnpg_image(db: Database) -> str:
    return f"ghcr.io/cloudnative-pg/postgresql:{db.params.get('version') or '17'}"


def secret_ref(db: Database, base: str) -> tuple[str, str]:
    """(nom du Secret, clé) qui porte l'URL de connexion de l'application."""
    if db.mode == "operator":
        return f"{base}-pg-app", "uri"
    return f"{base}-{db.id}", "url"


def app_env(dbs: list[Database], base: str) -> list[dict]:
    env = []
    for db in dbs:
        secret, key = secret_ref(db, base)
        env.append({"name": db.url_var, "valueFrom": {"secretKeyRef": {"name": secret, "key": key}}})
    return env


def instances_for(kind: str) -> int:
    return 3 if kind == "production" else 1


def gitops(ir: IR) -> bool:
    return ir.has("argo-cd") or ir.has("flux")


# ---- Helm
def helm_parts(ir: IR) -> tuple[dict, dict[str, str], list[dict], list[dict]]:
    """values.database, gabarits, variables d'environnement et initContainers de l'application."""
    dbs = kube_dbs(ir)
    if not dbs:
        return {}, {}, [], []
    values: dict = {}
    templates: dict[str, str] = {}
    base = "{{ .Release.Name }}"
    create = not gitops(ir)
    multi = ir.multi_env
    for db in dbs:
        k = _key(db)
        ref = f".Values.database.{k}"
        if db.mode == "self-hosted":
            values[k] = {"image": db.image, "storage": str(db.params.get("storage") or "10Gi"),
                         "createSecret": create, "password": ""}
            name = f"{base}-{db.id}"
            labels = {"app.kubernetes.io/name": f"{ir.app}-{db.id}", "app.kubernetes.io/instance": base}
            docs = statefulset_docs(db, name, "{{ " + ref + ".image }}", "{{ " + ref + ".storage }}", labels)
            secret = (
                f"{{{{- if {ref}.createSecret }}}}\n"
                "apiVersion: v1\nkind: Secret\nmetadata:\n"
                f"  name: {name}\ntype: Opaque\nstringData:\n"
                f'  password: {{{{ required "{ref[1:]}.password : mot de passe de {db.tool.name}" {ref}.password | quote }}}}\n'
                f"  url: {{{{ printf \"{_url_template(db)}\" {ref}.password .Release.Name | quote }}}}\n"
                "{{- end }}\n")
            templates[f"templates/{db.id}.yaml"] = secret + "---\n" + _unraw(dump_yaml_docs(docs, None))
        elif db.mode == "operator":
            kind = ir.envs[0].kind if not multi else "dev"
            values[k] = {"instances": instances_for(kind) if not multi else 1,
                         "storage": str(db.params.get("storage") or "10Gi"), "image": cnpg_image(db)}
            cluster = cnpg_cluster(db, f"{base}-pg", _raw("{{ " + ref + ".instances }}"),
                                   "{{ " + ref + ".storage }}", "{{ " + ref + ".image }}")
            templates[f"templates/{db.id}.yaml"] = _unraw(dump_yaml(cluster, None))
        else:
            values[k] = {"createSecret": create, "url": ""}
            name = f"{base}-{db.id}"
            templates[f"templates/{db.id}-secret.yaml"] = (
                f"{{{{- if {ref}.createSecret }}}}\n"
                "apiVersion: v1\nkind: Secret\nmetadata:\n"
                f"  name: {name}\ntype: Opaque\nstringData:\n"
                f'  url: {{{{ required "{ref[1:]}.url : URL de connexion à {db.tool.name}" {ref}.url | quote }}}}\n'
                "{{- end }}\n")
        ir.cover(db.id)
    env = app_env(dbs, base)
    init = _init_containers(ir, env, "{{ .Values.image.repository }}:{{ .Values.image.tag }}")
    return {"database": values}, templates, env, init


def _url_template(db: Database) -> str:
    """URL de connexion en gabarit printf : mot de passe puis nom de la release."""
    return db.url(f"%s-{db.id}", "%s").replace('"', '\\"')


def _init_containers(ir: IR, env: list[dict], image: str) -> list[dict]:
    command = migration_command(ir.project, ir.catalog)
    if not command:
        return []
    ir.cover(MIGRATIONS)
    return [{"name": "migrations", "image": image, "command": ["sh", "-c", command], "env": copy.deepcopy(env),
             "securityContext": {"allowPrivilegeEscalation": False}}]


def helm_env_values(ir: IR, env) -> dict:
    """Valeurs d'un environnement : nombre d'instances CloudNativePG."""
    out = {}
    for db in kube_dbs(ir):
        if db.mode == "operator":
            out[_key(db)] = {"instances": instances_for(env.kind)}
    return {"database": out} if out else {}


def helm_set_flags(ir: IR, env) -> str:
    """Options --set-string du déploiement Helm par la CI (mots de passe, URL des bases managées)."""
    flags = []
    for local, ci in secret_bindings(ir, env, [d for d in kube_dbs(ir) if d.mode != "operator"]):
        db = next(d for d in kube_dbs(ir) if local in (d.password_var, d.url_ci_var))
        field = "password" if db.mode == "self-hosted" else "url"
        flags.append(f'--set-string database.{_key(db)}.{field}="${ci}"')
    return (" " + " ".join(flags)) if flags else ""


# ---- Kustomize
def kustomize_parts(ir: IR) -> tuple[dict[str, str], list[str], list[dict], list[dict]]:
    """Fichiers de base, ressources à ajouter, variables d'environnement et initContainers."""
    dbs = kube_dbs(ir)
    if not dbs:
        return {}, [], [], []
    files: dict[str, str] = {}
    resources: list[str] = []
    app = ir.app
    single_kind = ir.envs[0].kind if not ir.multi_env else "dev"
    for db in dbs:
        if db.mode == "self-hosted":
            labels = {"app": f"{app}-{db.id}"}
            docs = statefulset_docs(db, f"{app}-{db.id}", db.image, str(db.params.get("storage") or "10Gi"), labels)
            files[f"{db.id}.yaml"] = dump_yaml_docs(docs)
            resources.append(f"{db.id}.yaml")
        elif db.mode == "operator":
            cluster = cnpg_cluster(db, f"{app}-pg", instances_for(single_kind),
                                   str(db.params.get("storage") or "10Gi"), cnpg_image(db))
            files[f"{db.id}.yaml"] = dump_yaml(cluster)
            resources.append(f"{db.id}.yaml")
        ir.cover(db.id)
    env = app_env(dbs, app)
    init = _init_containers(ir, env, f"{app}:latest")
    return files, resources, env, init


def kustomize_patches(ir: IR, env) -> list[dict]:
    out = []
    for db in kube_dbs(ir):
        if db.mode == "operator" and ir.multi_env:
            out.append({"target": {"kind": "Cluster", "name": f"{ir.app}-pg"},
                        "patch": f"- op: replace\n  path: /spec/instances\n  value: {instances_for(env.kind)}\n"})
    return out


def kubectl_secret_lines(ir: IR, env, ns: str) -> list[str]:
    """Commandes de la CI qui créent les Secrets de connexion avant kubectl apply -k."""
    dbs = [d for d in kube_dbs(ir) if d.mode != "operator"]
    if not dbs:
        return []
    bindings = dict(secret_bindings(ir, env, dbs))
    lines = [f"kubectl create namespace {ns} --dry-run=client -o yaml | kubectl apply -f -"]
    for db in dbs:
        name = f"{ir.app}-{db.id}"
        if db.mode == "self-hosted":
            pw = "$" + bindings[db.password_var]
            lits = f'--from-literal=password="{pw}" --from-literal=url="{db.url(name, pw)}"'
        else:
            lits = f'--from-literal=url="${bindings[db.url_ci_var]}"'
        lines.append(f"kubectl -n {ns} create secret generic {name} {lits} --dry-run=client -o yaml | kubectl apply -f -")
    return lines


def secret_name(ir: IR, db: Database) -> str:
    """Nom du Secret de connexion tel qu'il apparaît dans le cluster."""
    base = "<release>" if ir.has("helm") else ir.app
    return secret_ref(db, base)[0]


def gitops_note(ir: IR) -> None:
    dbs = [d for d in kube_dbs(ir) if d.mode != "operator"]
    if not dbs or not gitops(ir):
        return
    names = ", ".join(f"« {secret_name(ir, d)} » (clés {'password et url' if d.mode == 'self-hosted' else 'url'})"
                      for d in dbs)
    release = " ; la release Helm porte le nom de l'espace de noms" if ir.has("helm") else ""
    ir.notes.append(f"Bases de données avec GitOps : la CI ne touche pas au cluster ; créer dans chaque espace de noms "
                    f"le Secret {names}, par External Secrets ou SOPS{release}.")


# ----------------------------------------------------------------- Terraform
ENGINE_VERSIONS = {
    "aws-rds": {"postgres": "17", "mysql": "8.4", "mariadb": "11.4"},
    "cloud-sql": {"postgres": "17", "mysql": "8_4"},
    "azure-database": {"postgres": "16", "mysql": "8.0.21"},
}
RANDOM_PROVIDERS = ("cloud-sql", "azure-database", "scaleway-rdb")


def managed_dbs(ir: IR) -> list[Database]:
    return [d for d in all_dbs(ir) if d.mode == "managed"]


def needs_random(ir: IR) -> bool:
    return any(d.id in RANDOM_PROVIDERS for d in managed_dbs(ir))


def _instances(ir: IR, db: Database) -> list[tuple[str, object, dict]]:
    """(étiquette, environnement, paramètres) : une instance par nom distinct, la production d'abord."""
    seen: dict[str, tuple[str, object, dict]] = {}
    for env in ir.envs:
        params = env_params(db, ir.project, env)
        name = str(params.get("instance"))
        label = "db" if not ir.multi_env else "db_" + env.id.replace("-", "_")
        if name not in seen:
            seen[name] = (label, env, params)
    return list(seen.values())


def _password(label: str) -> str:
    return (f'resource "random_password" "{label}" {{\n  length           = 32\n  special          = true\n'
            f'  override_special = "-_.~"\n  min_lower        = 1\n  min_upper        = 1\n  min_numeric      = 1\n'
            f'  min_special      = 1\n}}')


def terraform_blocks(ir: IR) -> tuple[list[str], list[str], list[str]]:
    """Blocs de main.tf, variables et sorties pour les bases managées."""
    blocks: list[str] = []
    variables: list[str] = []
    outputs: list[str] = []
    for db in managed_dbs(ir):
        for label, env, p in _instances(ir, db):
            prod = env.kind == "production"
            title = f"{db.tool.name}" + (f" ({env.display})" if ir.multi_env else "")
            res, outs = _managed(ir, db, label, p, prod)
            blocks.append(f"# --- {title}\n{res}")
            outputs += outs
        ir.cover(db.id)
    return blocks, variables, outputs


def _managed(ir: IR, db: Database, label: str, p: dict, prod: bool) -> tuple[str, list[str]]:
    engine = str(p.get("engine") or "postgres")
    name = p.get("instance")
    user, dbname = db.user, db.name
    if db.id == "aws-rds":
        version = p.get("version") or ENGINE_VERSIONS["aws-rds"].get(engine, "17")
        snapshot = (f'  skip_final_snapshot         = false\n  final_snapshot_identifier   = "{name}-final"'
                    if prod else "  skip_final_snapshot         = true")
        res = f'''resource "aws_db_instance" "{label}" {{
  identifier                  = "{name}"
  engine                      = "{engine}"
  engine_version              = "{version}"
  instance_class              = "{p.get("instance_class", "db.t4g.micro")}"
  allocated_storage           = {int(p.get("storage_gb") or 20)}
  max_allocated_storage       = {int(p.get("storage_gb") or 20) * 5}
  storage_encrypted           = true
  db_name                     = "{dbname}"
  username                    = "{user}"
  manage_master_user_password = true
  db_subnet_group_name        = var.db_subnet_group
  vpc_security_group_ids      = var.db_security_group_ids
  multi_az                    = {str(prod).lower()}
  backup_retention_period     = {7 if prod else 1}
  deletion_protection         = {str(prod).lower()}
{snapshot}
}}'''
        outs = [f'output "{label}_endpoint" {{\n  value = aws_db_instance.{label}.address\n}}',
                f'output "{label}_secret_arn" {{\n  description = "Secret Secrets Manager du mot de passe principal"\n'
                f'  value       = aws_db_instance.{label}.master_user_secret[0].secret_arn\n}}']
        return res, outs
    if db.id == "cloud-sql":
        version = p.get("version") or ENGINE_VERSIONS["cloud-sql"].get(engine, "17")
        db_version = f"{'POSTGRES' if engine == 'postgres' else 'MYSQL'}_{str(version).replace('.', '_')}"
        region = ir.params("gcp").get("region", "europe-west9")
        backup = ("      point_in_time_recovery_enabled = true" if engine == "postgres"
                  else "      binary_log_enabled             = true")
        res = f'''resource "google_sql_database_instance" "{label}" {{
  name                = "{name}"
  database_version    = "{db_version}"
  region              = "{region}"
  deletion_protection = {str(prod).lower()}

  settings {{
    edition           = "ENTERPRISE"
    tier              = "{p.get("tier", "db-custom-1-3840")}"
    availability_type = "{"REGIONAL" if prod else "ZONAL"}"

    backup_configuration {{
      enabled                        = true
{backup}
    }}
  }}
}}

resource "google_sql_database" "{label}" {{
  name     = "{dbname}"
  instance = google_sql_database_instance.{label}.name
}}

{_password(label)}

resource "google_sql_user" "{label}" {{
  name     = "{user}"
  instance = google_sql_database_instance.{label}.name
  password = random_password.{label}.result
}}'''
        outs = [f'output "{label}_connection_name" {{\n  description = "Pour le Cloud SQL Auth Proxy"\n'
                f'  value       = google_sql_database_instance.{label}.connection_name\n}}',
                f'output "{label}_password" {{\n  value     = random_password.{label}.result\n  sensitive = true\n}}']
        return res, outs
    if db.id == "azure-database":
        version = p.get("version") or ENGINE_VERSIONS["azure-database"].get(engine, "16")
        sku = p.get("sku", "B_Standard_B1ms")
        if engine == "postgres":
            server, database = "azurerm_postgresql_flexible_server", "azurerm_postgresql_flexible_server_database"
            charset, collation, storage = "UTF8", "en_US.utf8", "  storage_mb             = 32768\n"
        else:
            server, database = "azurerm_mysql_flexible_server", "azurerm_mysql_flexible_database"
            charset, collation, storage = "utf8mb4", "utf8mb4_unicode_ci", ""
        res = f'''{_password(label)}

resource "{server}" "{label}" {{
  name                   = "{name}"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "{version}"
  administrator_login    = "{user}"
  administrator_password = random_password.{label}.result
  sku_name               = "{sku}"
{storage}  backup_retention_days  = {14 if prod else 7}
}}

resource "{database}" "{label}" {{
  name                = "{dbname}"
{"  server_id           = " + server + "." + label + ".id" if engine == "postgres" else "  resource_group_name = azurerm_resource_group.main.name" + chr(10) + "  server_name         = " + server + "." + label + ".name"}
  charset             = "{charset}"
  collation           = "{collation}"
}}'''
        outs = [f'output "{label}_host" {{\n  value = {server}.{label}.fqdn\n}}',
                f'output "{label}_password" {{\n  value     = random_password.{label}.result\n  sensitive = true\n}}']
        return res, outs
    if db.id == "scaleway-rdb":
        res = f'''{_password(label)}

resource "scaleway_rdb_instance" "{label}" {{
  name                      = "{name}"
  node_type                 = "{p.get("node_type", "DB-DEV-S")}"
  engine                    = "{engine}"
  is_ha_cluster             = {str(prod).lower()}
  disable_backup            = false
  backup_schedule_frequency = 24
  backup_schedule_retention = {14 if prod else 7}
  encryption_at_rest        = true
  user_name                 = "{user}"
  password                  = random_password.{label}.result
}}

resource "scaleway_rdb_database" "{label}" {{
  instance_id = scaleway_rdb_instance.{label}.id
  name        = "{dbname}"
}}'''
        outs = [f'output "{label}_endpoint" {{\n  value = scaleway_rdb_instance.{label}.load_balancer\n}}',
                f'output "{label}_password" {{\n  value     = random_password.{label}.result\n  sensitive = true\n}}']
        return res, outs
    # OVHcloud
    ovh_engine = "postgresql" if engine in ("postgresql", "postgres") else "mysql"
    user_res = ("ovh_cloud_project_database_postgresql_user" if ovh_engine == "postgresql"
                else "ovh_cloud_project_database_user")
    engine_line = "" if ovh_engine == "postgresql" else f'  engine       = "{ovh_engine}"\n'
    res = f'''resource "ovh_cloud_project_database" "{label}" {{
  service_name = var.ovh_service_name
  description  = "{name}"
  engine       = "{ovh_engine}"
  version      = "{p.get("version", "16")}"
  plan         = "{p.get("plan", "essential")}"
  flavor       = "{p.get("flavor", "db1-4")}"

  # Offres à plusieurs nœuds (business, enterprise…) : un bloc nodes par nœud.
  nodes {{
    region = "{p.get("region", "GRA")}"
  }}
}}

resource "ovh_cloud_project_database_database" "{label}" {{
  service_name = ovh_cloud_project_database.{label}.service_name
  engine       = ovh_cloud_project_database.{label}.engine
  cluster_id   = ovh_cloud_project_database.{label}.id
  name         = "{dbname}"
}}

resource "{user_res}" "{label}" {{
  service_name = ovh_cloud_project_database.{label}.service_name
{engine_line}  cluster_id   = ovh_cloud_project_database.{label}.id
  name         = "{user}"
}}'''
    outs = [f'output "{label}_endpoints" {{\n  value = ovh_cloud_project_database.{label}.endpoints\n}}',
            f'output "{label}_password" {{\n  value     = {user_res}.{label}.password\n  sensitive = true\n}}']
    return res, outs


# ----------------------------------------------------------------- notes
def notes(ir: IR) -> None:
    dbs = all_dbs(ir)
    if not dbs:
        return
    self_hosted = [d for d in dbs if d.mode == "self-hosted"]
    if self_hosted and ir.has("docker-compose"):
        names = ", ".join(d.tool.name for d in self_hosted)
        ir.notes.append(f"{names} : service Compose non publié sur l'hôte (réseau interne), données dans un volume "
                        f"nommé ; `{SECRETS_SCRIPT}` écrit les mots de passe et l'URL de connexion lus par les "
                        "conteneurs (env_file), à partir des variables CI.")
        if any(d.id in DUMPS for d in self_hosted):
            ir.notes.append(f"Sauvegardes : planifier `{BACKUP_SCRIPT}` sur chaque hôte (cron quotidien) et copier "
                            "les fichiers hors de la machine.")
    if any(d.mode == "operator" for d in dbs):
        ir.notes.append("CloudNativePG : l'opérateur est installé par platform/install.sh ; le Cluster crée le Secret "
                        "« <cluster>-app » (clé uri) lu par l'application. Sauvegardes : configurer le plugin "
                        "Barman Cloud vers un stockage objet, ou des instantanés de volumes.")
    if any(d.mode == "managed" for d in dbs):
        ir.notes.append("Bases managées : une instance par environnement ; après `apply`, composer l'URL de connexion "
                        "à partir des sorties Terraform (outputs.tf) et la déclarer en variable CI.")
    serverless = {"cloud-run": "Cloud Run : `gcloud run deploy --set-secrets DATABASE_URL=<secret>:latest` et, pour "
                               "Cloud SQL, `--add-cloudsql-instances <projet>:<région>:<instance>`",
                  "ecs-fargate": "ECS : bloc `secrets` de la définition de tâche (Secrets Manager ou Parameter Store)",
                  "azure-container-apps": "Azure Container Apps : `az containerapp secret set` puis "
                                          "`--set-env-vars DATABASE_URL=secretref:<nom>`"}
    for tid, how in serverless.items():
        if ir.has(tid):
            ir.notes.append(f"Connexion de l'application à la base sur un service serverless — {how}.")
    if any(d.engine.family == "document" and d.mode == "self-hosted" for d in dbs):
        ir.notes.append("MongoDB : l'application se connecte avec le compte administrateur initial ; créer un compte "
                        "dédié aux droits limités avant la production.")
