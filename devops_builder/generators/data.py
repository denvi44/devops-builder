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
    from .identity import all_compose_secrets
    return bool(compose_dbs(ir)) or bool(all_compose_secrets(ir))


def compose_bindings(ir: IR, env) -> list[tuple[str, str]]:
    """Variables lues par deploy/secrets.sh : bases, puis services de plateforme (fournisseur d'identité)."""
    from . import secrets
    from .identity import all_compose_secrets
    out = secret_bindings(ir, env, compose_dbs(ir))
    seen = {local for local, _ in out}
    where = f" ({env.display})" if ir.multi_env else ""
    for cs in all_compose_secrets(ir):
        if cs.var in seen:
            continue
        seen.add(cs.var)
        if secrets.source(ir) != "ci":
            out.append((cs.var, cs.var))
            continue
        ci = _var(ir, cs.var, env)
        ir.add_var(ci, f"{cs.description}{where}")
        out.append((cs.var, ci))
    return out


# ----------------------------------------------------------------- variables CI
def secret_bindings(ir: IR, env, dbs: list[Database]) -> list[tuple[str, str]]:
    """(variable lue par les scripts, variable CI) pour un environnement ; déclare les variables CI.

    Quand les valeurs viennent de SOPS ou de Vault / OpenBao, scripts/secrets-fetch.sh les exporte
    sous leur propre nom : aucune variable CI par valeur.
    """
    from . import secrets
    if secrets.source(ir) != "ci":
        return [(local, local) for local, _, _ in secrets.values(ir, dbs)]
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
    from .identity import all_compose_secrets
    dbs = compose_dbs(ir)
    extras = all_compose_secrets(ir)
    if not dbs and not extras:
        return {}
    names = list(dict.fromkeys([*_script_vars(dbs), *(cs.var for cs in extras)]))
    lines = ["#!/bin/sh", f"# {HEADER}",
             "# Écrit les fichiers de secrets lus par Docker Compose (env_file) à partir des variables",
             "# d'environnement ; appelé par la CI avant chaque déploiement, ou à la main sur un poste :",
             "#   " + " ".join(f"{v}=…" for v in names) + f" sh {SECRETS_SCRIPT} deploy/secrets",
             "set -eu", 'dir="${1:-secrets}"', "umask 077", 'mkdir -p "$dir"', ""]
    optional = {cs.var for cs in extras if cs.optional}
    for var in names:
        if var in optional:
            lines.append(f': "${{{var}:=}}"  # facultative au premier déploiement')
        else:
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
            app_lines += [f"{var}={part_value(db, key, db.id, pw)}" for var, key in db.parts()]
        else:
            app_lines.append(f"{db.url_var}=${db.url_ci_var}")
    by_file: dict[str, list[str]] = {}
    for cs in extras:
        by_file.setdefault(cs.file, []).append(f"{cs.key}=${cs.var}")
    for name, entries in by_file.items():
        lines += [f'cat > "$dir/{name}" <<EOF', *entries, "EOF"]
    if dbs:
        lines += ['cat > "$dir/app.env" <<EOF', *app_lines, "EOF"]
    lines += ['echo "Secrets écrits dans $dir"', ""]
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


DEV_DIR = "dev/db"
DEV_PASSWORD = "dev"  # poste de développement seulement : ports liés à 127.0.0.1
ADMINER_ENGINES = ("postgresql", "mariadb", "mysql")


def dev_version(db: Database) -> str:
    """Version locale proche de la production : celle de la brique, ou celle du moteur managé."""
    if db.mode != "managed":
        return db.version
    raw = str(db.params.get("version") or "")
    engine = str(db.params.get("engine") or "")
    m = re.search(r"(\d+(?:[._]\d+)?)$", engine) if not raw else None
    raw = raw or (m.group(1) if m else "")
    raw = raw.replace("_", ".")
    return raw if re.fullmatch(r"\d+(\.\d+)*", raw) else db.engine.default_version


def dev_files(ir: IR) -> dict[str, str]:
    """dev/db : les bases du projet pour le poste de développement, même moteur et même version."""
    dbs = all_dbs(ir)
    if not dbs:
        return {}
    services: dict[str, dict] = {}
    env_lines = [f"# {HEADER}", "# Connexion de l'application lancée sur le poste aux bases de dev/db/compose.yaml :",
                 f"#   docker compose -f {DEV_DIR}/compose.yaml up -d && set -a && . {DEV_DIR}/app.env && set +a"]
    used_ports: set[int] = set()
    for db in dbs:
        e = db.engine
        sid = e.id if e.id not in services else db.id
        port = e.port
        while port in used_ports:
            port += 1
        used_ports.add(port)
        svc: dict = {"image": f"{e.image}:{dev_version(db)}", "restart": "unless-stopped",
                     "ports": [f"127.0.0.1:{port}:{e.port}"]}
        env: dict[str, str] = {}
        if e.family in ("sql", "document"):
            env[e.user_env] = db.user
            env[e.db_env] = db.name
            env.update(dict(e.extra_env))
        if e.password_env:
            env[e.password_env] = DEV_PASSWORD
        if env:
            svc["environment"] = env
        if e.family == "key-value":
            binary = "valkey-server" if sid == "valkey" else "redis-server"
            svc["command"] = [binary, "--requirepass", DEV_PASSWORD]
        svc["volumes"] = [f"{sid}-dev:{e.data_path(dev_version(db))}"]
        if e.family in ("sql", "document"):
            svc["volumes"].append(f"./init/{sid}:/docker-entrypoint-initdb.d:ro")
        health = HEALTHCHECKS[e.id].replace(f"$${{{e.id.upper()}_PASSWORD}}", DEV_PASSWORD)
        svc["healthcheck"] = {"test": ["CMD-SHELL", health], "interval": "5s", "timeout": "5s", "retries": 20}
        services[sid] = svc
        url = db.url("127.0.0.1", DEV_PASSWORD).replace(f"127.0.0.1:{e.port}", f"127.0.0.1:{port}", 1)
        env_lines.append(f"{db.url_var}='{url}'")  # entre apostrophes : lu par le shell (& d'une URL JDBC)
        for var, key in db.parts():
            env_lines.append(f"{var}={str(port) if key == 'port' else part_value(db, key, '127.0.0.1', DEV_PASSWORD)}")
    if any(d.engine.id in ADMINER_ENGINES for d in dbs):
        services["adminer"] = {"image": "adminer:5", "profiles": ["outils"], "ports": ["127.0.0.1:8081:8080"],
                               "depends_on": [s for s in services if s in ADMINER_ENGINES]}
    volumes = {f"{sid}-dev": {} for sid in services if sid != "adminer"}
    files = {f"{DEV_DIR}/compose.yaml": dump_yaml(
        {"name": f"{ir.app}-dev", "services": services, "volumes": volumes},
        f"{HEADER} Bases du poste de développement : docker compose -f {DEV_DIR}/compose.yaml up -d"),
        f"{DEV_DIR}/app.env": "\n".join(env_lines) + "\n"}
    for db in dbs:
        if db.engine.family in ("sql", "document"):
            ext = ".js" if db.engine.family == "document" else ".sql"
            sid = db.engine.id if not any(f"{DEV_DIR}/init/{db.engine.id}/" in k for k in files) else db.id
            files[f"{DEV_DIR}/init/{sid}/README.md"] = (
                f"# Données de démonstration — {db.engine.label}\n\n"
                f"Les fichiers `*{ext}` (et `*.sh`) de ce dossier sont joués dans l'ordre alphabétique à la création "
                f"de la base locale, une seule fois. Pour les rejouer : `docker compose -f {DEV_DIR}/compose.yaml "
                f"down -v`, puis `up -d`.\n")
    return files


RESTORE_SCRIPT = "scripts/db-restore.sh"
RESTORES = {
    "postgresql": "pg_restore -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" --clean --if-exists --no-owner --exit-on-error",
    "mariadb": 'mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"',
    "mysql": 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"',
    "mongodb": ('mongorestore --archive --gzip --drop -u "$MONGO_INITDB_ROOT_USERNAME" '
                '-p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin'),
}


def restore_script(ir: IR) -> dict[str, str]:
    """Restauration d'une sauvegarde de db-backup.sh ; destructive, donc confirmée par --oui."""
    dbs = [d for d in compose_dbs(ir) if d.mode == "self-hosted" and d.id in RESTORES]
    if not dbs:
        return {}
    lines = ["#!/bin/sh", f"# {HEADER}",
             "# Restaure une sauvegarde de db-backup.sh dans la base du projet Compose ; la base est déduite du nom",
             "# du fichier. Le contenu actuel de la base est remplacé :",
             "#   db-restore.sh /opt/<projet> /var/backups/<projet>/<base>-<date>.<ext> --oui",
             "set -eu", 'dir="${1:?dossier du projet Compose, ex. /opt/mon-app}"',
             'file="${2:?fichier de sauvegarde}"', '[ -f "$file" ] || { echo "Fichier absent : $file" >&2; exit 1; }',
             'project="$(basename "$dir")"',
             'dc() { docker compose --project-directory "$dir" -p "$project" "$@"; }',
             'case "$(basename "$file")" in']
    for db in dbs:
        lines.append(f"  {db.id}-*) service={db.id}; cmd='{RESTORES[db.id]}' ;;")
    lines += ['  *) echo "Base inconnue pour $(basename "$file") (préfixe attendu : '
              + ", ".join(f"{d.id}-" for d in dbs) + ')" >&2; exit 2 ;;', "esac",
              'if [ "${3:-}" != "--oui" ]; then',
              '  echo "La base $service de $project va être remplacée par $file : relancer avec --oui." >&2',
              "  exit 1", "fi",
              'dc exec -T "$service" sh -c "$cmd" < "$file"',
              'echo "$service restaurée depuis $file"', ""]
    return {RESTORE_SCRIPT: "\n".join(lines)}


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


BARMAN_PLUGIN = "barman-cloud.cloudnative-pg.io"


def cnpg_cluster(db: Database, name: str, instances, storage: str, image: str, store: str | None = None) -> dict:
    spec: dict = {"instances": instances, "imageName": image, "storage": {"size": storage},
                  "bootstrap": {"initdb": {"database": db.name, "owner": db.user}}}
    if store:  # archivage continu des WAL par le plugin Barman Cloud
        spec["plugins"] = [{"name": BARMAN_PLUGIN, "isWALArchiver": True, "parameters": {"barmanObjectName": store}}]
    return {"apiVersion": "postgresql.cnpg.io/v1", "kind": "Cluster", "metadata": {"name": name}, "spec": spec}


BACKUP_SECRET = "{app}-backup-credentials"


def backup_credentials(ir: IR, dest: str) -> dict:
    """Identifiants de l'ObjectStore : identité de la pile (EKS, GKE) ou Secret à créer."""
    cloud = cnpg_backup_cloud(ir) if not cnpg_params(ir).get("backup_destination") else None
    secret = BACKUP_SECRET.format(app=ir.app)
    if dest.startswith("s3://"):
        if cloud == "aws":
            return {"s3Credentials": {"inheritFromIAMRole": True}}
        creds: dict = {"s3Credentials": {"accessKeyId": {"name": secret, "key": "ACCESS_KEY_ID"},
                                         "secretAccessKey": {"name": secret, "key": "ACCESS_SECRET_KEY"}}}
        endpoint = str(cnpg_params(ir).get("backup_endpoint") or "")
        if endpoint:
            creds["endpointURL"] = endpoint
        return creds
    if dest.startswith("gs://"):
        if cloud == "gcp":
            return {"googleCredentials": {"gkeEnvironment": True}}
        return {"googleCredentials": {"applicationCredentials": {"name": secret, "key": "credentials.json"}}}
    return {"azureCredentials": {"storageAccount": {"name": secret, "key": "AZURE_STORAGE_ACCOUNT"},
                                 "storageKey": {"name": secret, "key": "AZURE_STORAGE_KEY"}}}


def cnpg_params(ir: IR) -> dict:
    db = next((d for d in kube_dbs(ir) if d.mode == "operator"), None)
    return db.params if db else {}


def backup_needs_secret(ir: IR) -> bool:
    target = cnpg_backup(ir)
    return bool(target) and not any(k in str(backup_credentials(ir, target[0])) for k in
                                    ("inheritFromIAMRole", "gkeEnvironment"))


def object_store(ir: IR, name: str, ns: str) -> dict:
    dest = cnpg_backup(ir)[0]
    return {"apiVersion": "barmancloud.cnpg.io/v1", "kind": "ObjectStore", "metadata": {"name": name},
            "spec": {"retentionPolicy": "30d",
                     "configuration": {"destinationPath": f"{dest}/{ns}", **backup_credentials(ir, dest),
                                       "wal": {"compression": "gzip"}}}}


def scheduled_backup(cluster: str) -> dict:
    return {"apiVersion": "postgresql.cnpg.io/v1", "kind": "ScheduledBackup", "metadata": {"name": f"{cluster}-quotidien"},
            "spec": {"schedule": "0 0 3 * * *", "backupOwnerReference": "self", "cluster": {"name": cluster},
                     "method": "plugin", "pluginConfiguration": {"name": BARMAN_PLUGIN}}}


def cnpg_image(db: Database) -> str:
    return f"ghcr.io/cloudnative-pg/postgresql:{db.params.get('version') or '17'}"


def secret_ref(db: Database, base: str) -> tuple[str, str]:
    """(nom du Secret, clé) qui porte l'URL de connexion de l'application."""
    if db.mode == "operator":  # Secret « <cluster>-app » de CloudNativePG
        return f"{base}-pg-app", "jdbc-uri" if db.fmt == "jdbc" else "uri"
    return f"{base}-{db.id}", "url"


def part_value(db: Database, key: str, host: str, password: str) -> str:
    """Valeur d'une variable séparée (format parts)."""
    return {"host": host, "port": str(db.engine.port), "name": db.name, "user": db.user,
            "password": password}[key]


CNPG_KEYS = {"host": "host", "port": "port", "name": "dbname", "user": "user", "password": "password"}


def app_env(dbs: list[Database], base: str) -> list[dict]:
    env = []
    for db in dbs:
        secret, key = secret_ref(db, base)
        env.append({"name": db.url_var, "valueFrom": {"secretKeyRef": {"name": secret, "key": key}}})
        for var, part in db.parts():
            if db.mode == "operator":
                env.append({"name": var, "valueFrom": {"secretKeyRef": {"name": secret, "key": CNPG_KEYS[part]}}})
            elif part == "password":
                env.append({"name": var, "valueFrom": {"secretKeyRef": {"name": secret, "key": "password"}}})
            else:
                env.append({"name": var, "value": part_value(db, part, f"{base}-{db.id}", "")})
    return env


def instances_for(kind: str) -> int:
    return 3 if kind == "production" else 1


def cnpg_backup(ir: IR) -> tuple[str, str] | None:
    """(destination, libellé) des sauvegardes CloudNativePG, ou None : rien de configuré."""
    dbs = [d for d in kube_dbs(ir) if d.mode == "operator"]
    if not dbs:
        return None
    dest = str(dbs[0].params.get("backup_destination") or "")
    if not dest:
        tool = cnpg_backup_cloud(ir)
        if tool == "aws":
            dest = f"s3://{ir.app}-db-backups"
        elif tool == "gcp":
            dest = f"gs://{ir.app}-db-backups"
    if not dest:
        return None
    return dest.rstrip("/"), dest.rstrip("/")


def cnpg_backup_cloud(ir: IR) -> str | None:
    """Cloud dont la pile crée le bucket et l'identité des sauvegardes (EKS, GKE avec l'IaC)."""
    from .iac import backend_tool  # noqa: F401 — la pile existe dès qu'un fournisseur est configuré
    providers = {p.id for p in ir.providers}
    if ir.has("eks") and "aws" in providers:
        return "aws"
    if ir.has("gke") and "gcp" in providers:
        return "gcp"
    return None


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
    from . import secrets
    create = not gitops(ir) and not secrets.eso(ir)
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
            store = f"{base}-backups" if cnpg_backup(ir) else None
            cluster = cnpg_cluster(db, f"{base}-pg", _raw("{{ " + ref + ".instances }}"),
                                   "{{ " + ref + ".storage }}", "{{ " + ref + ".image }}", store)
            docs = [cluster]
            if store:
                docs += [object_store(ir, store, "{{ .Release.Namespace }}"), scheduled_backup(f"{base}-pg")]
            templates[f"templates/{db.id}.yaml"] = _unraw(dump_yaml_docs(docs, None))
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
    eso_template = secrets.eso_helm_template(ir, dbs)
    if eso_template:
        templates["templates/externalsecrets.yaml"] = eso_template
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
    from . import secrets
    if secrets.eso(ir):
        return ""  # External Secrets écrit les Secrets du chart
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
            store = f"{app}-backups" if cnpg_backup(ir) else None
            cluster = cnpg_cluster(db, f"{app}-pg", instances_for(single_kind),
                                   str(db.params.get("storage") or "10Gi"), cnpg_image(db), store)
            files[f"{db.id}.yaml"] = dump_yaml_docs([cluster, scheduled_backup(f"{app}-pg")]) if store \
                else dump_yaml(cluster)
            resources.append(f"{db.id}.yaml")
        ir.cover(db.id)
    env = app_env(dbs, app)
    init = _init_containers(ir, env, f"{app}:latest")
    return files, resources, env, init


def kustomize_external_secrets(ir: IR, env) -> str | None:
    """ExternalSecret de l'overlay d'un environnement (clé du coffre : espace de noms/brique)."""
    from . import secrets
    if not secrets.eso(ir):
        return None
    docs = secrets.external_secrets(ir, kube_dbs(ir), lambda d: f"{ir.app}-{d.id}", ir.namespace(env), False)
    return dump_yaml_docs(docs) if docs else None


def pod_identity_addons(ir: IR) -> list[str]:
    """Agent EKS Pod Identity, une fois par cluster, dès qu'une identité de charge de travail s'en sert."""
    from .iac import cluster_instances
    from .secrets import eso_identity
    if not ir.has("eks") or not (eso_identity(ir) == "aws-secrets-manager" or
                                  (cnpg_backup(ir) and cnpg_backup_cloud(ir) == "aws" and
                                   not cnpg_params(ir).get("backup_destination"))):
        return []
    return [f'''# --- EKS Pod Identity (identités de charge de travail)
resource "aws_eks_addon" "pod_identity{sfx}" {{
  cluster_name = module.eks{sfx}.cluster_name
  addon_name   = "eks-pod-identity-agent"
}}''' for sfx, _ in cluster_instances(ir, "eks")]


def backup_terraform_blocks(ir: IR) -> tuple[list[str], list[str]]:
    """Bucket des sauvegardes CloudNativePG et accès du compte de service de chaque Cluster."""
    from .iac import cluster_instances
    cloud = cnpg_backup_cloud(ir)
    if not cnpg_backup(ir) or not cloud or cnpg_params(ir).get("backup_destination"):
        return [], []
    bucket = f"{ir.app}-db-backups"
    namespaces = sorted({ir.namespace(e) for e in ir.envs})
    sa = f"{ir.app}-pg"  # CloudNativePG crée un compte de service au nom du Cluster
    title = "# --- Sauvegardes CloudNativePG (plugin Barman Cloud)"
    if cloud == "aws":
        blocks = [f'''{title}
resource "aws_s3_bucket" "db_backups" {{
  bucket = "{bucket}"
}}

resource "aws_s3_bucket_versioning" "db_backups" {{
  bucket = aws_s3_bucket.db_backups.id
  versioning_configuration {{
    status = "Enabled"
  }}
}}

resource "aws_s3_bucket_public_access_block" "db_backups" {{
  bucket                  = aws_s3_bucket.db_backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}}

resource "aws_iam_role" "db_backups" {{
  name = "{ir.app}-db-backups"
  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect    = "Allow"
      Principal = {{ Service = "pods.eks.amazonaws.com" }}
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }}]
  }})
}}

resource "aws_iam_role_policy" "db_backups" {{
  name = "sauvegardes"
  role = aws_iam_role.db_backups.id
  policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketLocation"]
      Resource = [aws_s3_bucket.db_backups.arn, "${{aws_s3_bucket.db_backups.arn}}/*"]
    }}]
  }})
}}''']
        for sfx, _ in cluster_instances(ir, "eks"):
            for ns in namespaces:
                label = (sfx + "_" + ns.replace("-", "_")).lstrip("_")
                blocks.append(f'''resource "aws_eks_pod_identity_association" "db_backups_{label}" {{
  cluster_name    = module.eks{sfx}.cluster_name
  namespace       = "{ns}"
  service_account = "{sa}"
  role_arn        = aws_iam_role.db_backups.arn
}}''')
        outputs = ['output "db_backups_bucket" {\n  value = aws_s3_bucket.db_backups.bucket\n}']
    else:
        region = ir.params("gcp").get("region", "europe-west9")
        blocks = [f'''{title}
data "google_project" "backups" {{
  project_id = var.gcp_project_id
}}

resource "google_storage_bucket" "db_backups" {{
  name                        = "{bucket}"
  location                    = "{region}"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {{
    enabled = true
  }}
}}''']
        for ns in namespaces:
            label = ns.replace("-", "_")
            blocks.append(f'''resource "google_storage_bucket_iam_member" "db_backups_{label}" {{
  bucket = google_storage_bucket.db_backups.name
  role   = "roles/storage.objectAdmin"
  member = "principal://iam.googleapis.com/projects/${{data.google_project.backups.number}}/locations/global/workloadIdentityPools/${{var.gcp_project_id}}.svc.id.goog/subject/ns/{ns}/sa/{sa}"
}}''')
        outputs = ['output "db_backups_bucket" {\n  value = google_storage_bucket.db_backups.name\n}']
    return blocks, outputs


def kustomize_object_store(ir: IR, env) -> str | None:
    """ObjectStore des sauvegardes CloudNativePG d'un environnement (chemin propre à l'espace de noms)."""
    if not cnpg_backup(ir):
        return None
    return dump_yaml(object_store(ir, f"{ir.app}-backups", ir.namespace(env)))


def kustomize_patches(ir: IR, env) -> list[dict]:
    out = []
    for db in kube_dbs(ir):
        if db.mode == "operator" and ir.multi_env:
            out.append({"target": {"kind": "Cluster", "name": f"{ir.app}-pg"},
                        "patch": f"- op: replace\n  path: /spec/instances\n  value: {instances_for(env.kind)}\n"})
    return out


def kubectl_secret_lines(ir: IR, env, ns: str) -> list[str]:
    """Commandes de la CI qui créent les Secrets de connexion avant kubectl apply -k."""
    from . import secrets
    dbs = [d for d in kube_dbs(ir) if d.mode != "operator"]
    if not dbs:
        return []
    lines = [f"kubectl create namespace {ns} --dry-run=client -o yaml | kubectl apply -f -"]
    if secrets.eso(ir):
        return lines  # les ExternalSecret de l'overlay font le reste
    bindings = dict(secret_bindings(ir, env, dbs))
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
    from . import secrets
    dbs = [d for d in kube_dbs(ir) if d.mode != "operator"]
    if not dbs or not gitops(ir) or secrets.eso(ir):
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


def _azure_db_body(engine: str, server: str, label: str, dbname: str, charset: str, collation: str) -> str:
    if engine == "postgres":
        rows = [("name", f'"{dbname}"'), ("server_id", f"{server}.{label}.id")]
    else:
        rows = [("name", f'"{dbname}"'), ("resource_group_name", "azurerm_resource_group.main.name"),
                ("server_name", f"{server}.{label}.name")]
    rows += [("charset", f'"{charset}"'), ("collation", f'"{collation}"')]
    width = max(len(k) for k, _ in rows)
    return "\n".join(f"  {k.ljust(width)} = {v}" for k, v in rows)


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
{_azure_db_body(engine, server, label, dbname, charset, collation)}
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
SERVERLESS_SECRETS = {
    "cloud-run": "Cloud Run : `gcloud run deploy --set-secrets DATABASE_URL=<secret>:latest` et, pour "
                 "Cloud SQL, `--add-cloudsql-instances <projet>:<région>:<instance>`",
    "ecs-fargate": "ECS : bloc `secrets` de la définition de tâche (Secrets Manager ou Parameter Store)",
    "azure-container-apps": "Azure Container Apps : `az containerapp secret set` puis "
                            "`--set-env-vars DATABASE_URL=secretref:<nom>`",
}


def notes(ir: IR) -> None:
    dbs = all_dbs(ir)
    if not dbs:
        return
    from . import secrets
    ir.notes.append(f"Poste de développement : `docker compose -f {DEV_DIR}/compose.yaml up -d` lance les bases du "
                    f"projet (même version), `{DEV_DIR}/app.env` donne leurs variables de connexion.")
    self_hosted = [d for d in dbs if d.mode == "self-hosted"]
    origin = {"ci": "des variables CI", "sops": "des fichiers SOPS déchiffrés par la CI",
              "vault": "du coffre, lu par la CI"}[secrets.source(ir)]
    if self_hosted and ir.has("docker-compose"):
        names = ", ".join(d.tool.name for d in self_hosted)
        ir.notes.append(f"{names} : service Compose non publié sur l'hôte (réseau interne), données dans un volume "
                        f"nommé ; `{SECRETS_SCRIPT}` écrit les mots de passe et l'URL de connexion lus par les "
                        f"conteneurs (env_file), à partir {origin}.")
        if any(d.id in DUMPS for d in self_hosted):
            ir.notes.append(f"Sauvegardes : planifier `{BACKUP_SCRIPT}` sur chaque hôte (cron quotidien) et copier "
                            "les fichiers hors de la machine.")
    if any(d.mode == "operator" for d in dbs):
        target = cnpg_backup(ir)
        backup = (f"Sauvegardes : plugin Barman Cloud vers {target[0]}/<espace de noms> (archivage continu des WAL, "
                  "sauvegarde quotidienne, rétention 30 jours)." if target else
                  "Sauvegardes : renseigner « Destination des sauvegardes » dans la brique (plugin Barman Cloud), ou "
                  "des instantanés de volumes.")
        ir.notes.append("CloudNativePG : l'opérateur est installé par platform/install.sh ; le Cluster crée le Secret "
                        f"« <cluster>-app » (clés uri, jdbc-uri, host, user, password) lu par l'application. {backup}")
    written = {d.id for d in secrets.tf_dbs(ir, compose_dbs(ir))}
    if any(d.mode == "managed" and d.id not in written for d in dbs):
        ir.notes.append("Bases managées : une instance par environnement ; après `apply`, composer l'URL de connexion "
                        "à partir des sorties Terraform (outputs.tf) et la déclarer en variable CI.")
    for tid, how in SERVERLESS_SECRETS.items():
        if ir.has(tid):
            ir.notes.append(f"Connexion de l'application à la base sur un service serverless — {how}.")
    if any(d.engine.family == "document" and d.mode == "self-hosted" for d in dbs):
        ir.notes.append("MongoDB : l'application se connecte avec le compte administrateur initial ; créer un compte "
                        "dédié aux droits limités avant la production.")
