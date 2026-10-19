# SPDX-License-Identifier: Apache-2.0
"""Base de données dédiée à un outil de plateforme (Gitea, SonarQube, Grafana, Harbor).

Par défaut, l'outil garde sa base intégrée (SQLite pour Gitea et Grafana, H2 pour SonarQube, PostgreSQL du chart pour
Harbor). Le paramètre « Base de données » de la brique demande une base à lui, une par instance, parmi les moteurs que
l'outil sait utiliser (PostgreSQL, MariaDB, MySQL) : un service Compose `<instance>-db` avec son volume et son mot de
passe (secrets/), ou, sur Kubernetes, un Cluster CloudNativePG pour PostgreSQL (sinon un StatefulSet) dans l'espace de
noms de l'outil, que le chart Helm de l'outil utilise à la place de sa base.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import IR
from .common import dump_yaml_docs
from .identity import ComposeSecret, compose_target, kube_target

DB_IMAGE = "postgres:17"
# Outil → (utilisateur et base, moteurs acceptés)
TOOLS = {"gitea": ("gitea", ("postgresql", "mariadb", "mysql")), "sonarqube": ("sonarqube", ("postgresql",)),
         "grafana": ("grafana", ("postgresql", "mariadb", "mysql")), "harbor": ("harbor", ("postgresql",))}
# Clé du mot de passe dans le conteneur de l'outil (Compose)
PASSWORD_KEY = {"gitea": "GITEA__database__PASSWD", "sonarqube": "SONAR_JDBC_PASSWORD",
                "grafana": "GF_DATABASE_PASSWORD"}
PARAM = "database"
SQL_TYPE = {"postgresql": "postgres", "mariadb": "mysql", "mysql": "mysql"}   # « type » attendu par Gitea et Grafana


@dataclass(frozen=True)
class ToolDb:
    tool: str
    brick: object

    @property
    def sid(self) -> str:
        return self.brick.service_id

    @property
    def name(self) -> str:   # utilisateur et base
        return TOOLS[self.tool][0]

    @property
    def engine(self) -> str:
        return str(self.brick.params.get(PARAM))

    @property
    def port(self) -> int:
        from ..databases import ENGINES
        return ENGINES[self.engine].port

    @property
    def image(self) -> str:
        from ..databases import ENGINES
        return DB_IMAGE if self.engine == "postgresql" else ENGINES[self.engine].image + ":" + \
            ENGINES[self.engine].default_version

    @property
    def var(self) -> str:
        return self.sid.upper().replace("-", "_") + "_DB_PASSWORD"


def dedicated(ir: IR) -> list[ToolDb]:
    """Briques qui demandent un PostgreSQL à elles."""
    return [ToolDb(t, b) for t in TOOLS for b in ir.project.bricks_for(t)
            if (b.params or {}).get(PARAM) in TOOLS[t][1]]


# ------------------------------------------------------------------ Compose
def compose_secrets(ir: IR) -> list[ComposeSecret]:
    if not compose_target(ir):
        return []
    from ..databases import ENGINES
    out = []
    for d in dedicated(ir):
        if d.tool not in PASSWORD_KEY:   # Harbor n'a pas de service Compose
            continue
        what = f"Mot de passe de la base {ENGINES[d.engine].label} de {ir.catalog[d.tool].name}" + (
            f" ({d.brick.instance})" if d.brick.instance else "")
        out += [ComposeSecret(d.var, f"{d.sid}-db.env", ENGINES[d.engine].password_env, what, tool=d.tool),
                ComposeSecret(d.var, f"{d.sid}.env", PASSWORD_KEY[d.tool], what, tool=d.tool)]
    return out


def _tool_env(d: ToolDb) -> dict[str, str]:
    host = f"{d.sid}-db"
    if d.tool == "gitea":
        return {"GITEA__database__DB_TYPE": SQL_TYPE[d.engine], "GITEA__database__HOST": f"{host}:{d.port}",
                "GITEA__database__NAME": d.name, "GITEA__database__USER": d.name}
    if d.tool == "sonarqube":
        return {"SONAR_JDBC_URL": f"jdbc:postgresql://{host}:{d.port}/{d.name}", "SONAR_JDBC_USERNAME": d.name}
    return {"GF_DATABASE_TYPE": SQL_TYPE[d.engine], "GF_DATABASE_HOST": f"{host}:{d.port}",
            "GF_DATABASE_NAME": d.name, "GF_DATABASE_USER": d.name}


def _compose_db(d: ToolDb) -> dict:
    from ..databases import ENGINES, HEALTHCHECKS
    e = ENGINES[d.engine]
    health = HEALTHCHECKS[d.engine]
    return {
        "image": d.image, "restart": "unless-stopped",
        "environment": {e.user_env: d.name, e.db_env: d.name, **dict(e.extra_env)},
        "env_file": [f"secrets/{d.sid}-db.env"], "volumes": [f"{d.sid}-db-data:{e.data_path(d.image.split(':')[1])}"],
        "healthcheck": {"test": ["CMD-SHELL", health], "interval": "10s", "timeout": "5s", "retries": 10}}


def apply_compose(ir: IR, services: dict[str, dict]) -> dict[str, dict]:
    """Ajoute le service de base de chaque outil concerné et relie l'outil à sa base."""
    if not compose_target(ir):
        return services
    out = dict(services)
    for d in dedicated(ir):
        if d.sid not in out or d.tool not in PASSWORD_KEY:
            continue
        svc = dict(out[d.sid])
        svc["environment"] = {**svc.get("environment", {}), **_tool_env(d)}
        files = list(svc.get("env_file", []))
        if f"secrets/{d.sid}.env" not in files:
            files.append(f"secrets/{d.sid}.env")
        svc["env_file"] = files
        svc["depends_on"] = {**svc.get("depends_on", {}), f"{d.sid}-db": {"condition": "service_healthy"}}
        out[d.sid] = svc
        out[f"{d.sid}-db"] = _compose_db(d)
    return out


# ------------------------------------------------------------------ Kubernetes
def _namespace(d: ToolDb) -> str:
    from .entree import namespace_of
    return namespace_of(d.tool, d.brick)


def _operator(ir: IR, d: ToolDb) -> bool:
    """CloudNativePG ne gère que PostgreSQL."""
    return d.engine == "postgresql" and ir.has("cloudnative-pg")


def _connection(ir: IR, d: ToolDb) -> tuple[str, str]:
    """(hôte du service, Secret qui porte « username » et « password »)."""
    if _operator(ir, d):
        return f"{d.sid}-pg-rw", f"{d.sid}-pg-app"
    return f"{d.sid}-db", f"{d.sid}-db"


def kube_files(ir: IR) -> dict[str, str]:
    if not kube_target(ir):
        return {}
    out = {}
    for d in dedicated(ir):
        ns = _namespace(d)
        if _operator(ir, d):
            docs = [{"apiVersion": "postgresql.cnpg.io/v1", "kind": "Cluster",
                     "metadata": {"name": f"{d.sid}-pg", "namespace": ns},
                     "spec": {"instances": 1, "storage": {"size": "5Gi"},
                              "bootstrap": {"initdb": {"database": d.name, "owner": d.name}}}}]
        else:
            from ..databases import ENGINES, Database
            from .data import statefulset_docs
            version = d.image.split(":")[1]
            db = Database(ir.catalog[d.engine], ENGINES[d.engine], "self-hosted",
                          {"database": d.name, "user": d.name, "version": version})
            docs = statefulset_docs(db, f"{d.sid}-db", d.image, "5Gi", {"app": f"{d.sid}-db"})
            for doc in docs:
                doc["metadata"]["namespace"] = ns
        out[f"platform/db-{d.sid}.yaml"] = dump_yaml_docs(docs)
    if out:
        ir.notes.append("Bases dédiées : une base par outil dans platform/db-<instance>.yaml (Cluster CloudNativePG "
                        "pour PostgreSQL avec l'opérateur, sinon StatefulSet). Les réglages Helm qui branchent l'outil "
                        "sur sa base (clés --set de install.sh) suivent la documentation de chaque chart : les "
                        "vérifier à la première installation.")
    return out


def kube_install(ir: IR, tool: str, brick) -> tuple[list[str], str]:
    """(lignes avant le helm install, options Helm) de l'outil, pour platform/install.sh."""
    if not kube_target(ir):
        return [], ""
    d = next((x for x in dedicated(ir) if x.tool == tool and x.brick is brick), None)
    if d is None:
        return [], ""
    ns = _namespace(d)
    host, secret = _connection(ir, d)
    pre = [f"kubectl create namespace {ns} --dry-run=client -o yaml | kubectl apply -f -"]
    if not _operator(ir, d):   # sans l'opérateur : le Secret est tiré une fois
        pre += [f"if ! kubectl -n {ns} get secret {secret} >/dev/null 2>&1; then  # mot de passe tiré une fois",
                f"  kubectl -n {ns} create secret generic {secret} --from-literal=username={d.name} "
                '--from-literal=password="$(openssl rand -hex 24)"', "fi"]
    pre.append(f'kubectl apply -f "$(dirname "$0")/db-{d.sid}.yaml"')
    return pre, _helm_args(tool, d, host, secret)


def _helm_args(tool: str, d: ToolDb, host: str, secret: str) -> str:
    port = d.port
    if tool == "gitea":
        env = "gitea.additionalConfigFromEnvs[0]"
        return (" --set postgresql-ha.enabled=false --set postgresql.enabled=false"
                f" --set gitea.config.database.DB_TYPE={SQL_TYPE[d.engine]}"
                f" --set gitea.config.database.HOST={host}:{port} --set gitea.config.database.NAME={d.name}"
                f" --set gitea.config.database.USER={d.name} --set '{env}.name=GITEA__DATABASE__PASSWD'"
                f" --set '{env}.valueFrom.secretKeyRef.name={secret}' --set '{env}.valueFrom.secretKeyRef.key=password'")
    if tool == "sonarqube":
        return (" --set postgresql.enabled=false --set jdbcOverwrite.enable=true"
                f" --set jdbcOverwrite.jdbcUrl=jdbc:postgresql://{host}:{port}/{d.name}"
                f" --set jdbcOverwrite.jdbcUsername={d.name} --set jdbcOverwrite.jdbcSecretName={secret}"
                " --set jdbcOverwrite.jdbcSecretPasswordKey=password")
    if tool == "harbor":
        return (f" --set database.type=external --set database.external.host={host}"
                f" --set database.external.port={port} --set database.external.username={d.name}"
                f" --set database.external.coreDatabase={d.name} --set database.external.existingSecret={secret}")
    env = "envValueFrom.GF_DATABASE_PASSWORD.secretKeyRef"
    return (f" --set 'grafana\\.ini.database.type={SQL_TYPE[d.engine]}'"
            f" --set 'grafana\\.ini.database.host={host}:{port}' --set 'grafana\\.ini.database.name={d.name}'"
            f" --set 'grafana\\.ini.database.user={d.name}' --set '{env}.name={secret}' --set '{env}.key=password'")
