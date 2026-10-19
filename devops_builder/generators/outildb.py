# SPDX-License-Identifier: Apache-2.0
"""Base PostgreSQL dédiée à un outil de plateforme (Gitea, SonarQube, Grafana).

Par défaut, l'outil garde sa base intégrée (SQLite pour Gitea et Grafana, H2 pour SonarQube). Le paramètre
« Base de données » de la brique demande un PostgreSQL à lui, une par instance : un service Compose
`<instance>-db` avec son volume et son mot de passe (secrets/), ou, sur Kubernetes, un Cluster CloudNativePG (ou, sans
l'opérateur, un StatefulSet) dans l'espace de noms de l'outil, que le chart Helm de l'outil utilise à la place de sa base.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import IR
from .common import dump_yaml_docs
from .identity import ComposeSecret, compose_target, kube_target

DB_IMAGE = "postgres:17"
# Outil → (utilisateur et base, clé du mot de passe dans le conteneur de l'outil)
TOOLS = {"gitea": "gitea", "sonarqube": "sonarqube", "grafana": "grafana"}
PASSWORD_KEY = {"gitea": "GITEA__database__PASSWD", "sonarqube": "SONAR_JDBC_PASSWORD",
                "grafana": "GF_DATABASE_PASSWORD"}
PARAM = "database"
DEDICATED = "postgresql"


@dataclass(frozen=True)
class ToolDb:
    tool: str
    brick: object

    @property
    def sid(self) -> str:
        return self.brick.service_id

    @property
    def name(self) -> str:   # utilisateur et base
        return TOOLS[self.tool]

    @property
    def var(self) -> str:
        return self.sid.upper().replace("-", "_") + "_DB_PASSWORD"


def dedicated(ir: IR) -> list[ToolDb]:
    """Briques qui demandent un PostgreSQL à elles."""
    return [ToolDb(t, b) for t in TOOLS for b in ir.project.bricks_for(t)
            if (b.params or {}).get(PARAM) == DEDICATED]


# ------------------------------------------------------------------ Compose
def compose_secrets(ir: IR) -> list[ComposeSecret]:
    if not compose_target(ir):
        return []
    out = []
    for d in dedicated(ir):
        what = f"Mot de passe de la base PostgreSQL de {ir.catalog[d.tool].name}" + (
            f" ({d.brick.instance})" if d.brick.instance else "")
        out += [ComposeSecret(d.var, f"{d.sid}-db.env", "POSTGRES_PASSWORD", what, tool=d.tool),
                ComposeSecret(d.var, f"{d.sid}.env", PASSWORD_KEY[d.tool], what, tool=d.tool)]
    return out


def _tool_env(d: ToolDb) -> dict[str, str]:
    host = f"{d.sid}-db"
    if d.tool == "gitea":
        return {"GITEA__database__DB_TYPE": "postgres", "GITEA__database__HOST": f"{host}:5432",
                "GITEA__database__NAME": d.name, "GITEA__database__USER": d.name}
    if d.tool == "sonarqube":
        return {"SONAR_JDBC_URL": f"jdbc:postgresql://{host}:5432/{d.name}", "SONAR_JDBC_USERNAME": d.name}
    return {"GF_DATABASE_TYPE": "postgres", "GF_DATABASE_HOST": f"{host}:5432", "GF_DATABASE_NAME": d.name,
            "GF_DATABASE_USER": d.name}


def apply_compose(ir: IR, services: dict[str, dict]) -> dict[str, dict]:
    """Ajoute le service de base de chaque outil concerné et relie l'outil à sa base."""
    if not compose_target(ir):
        return services
    out = dict(services)
    for d in dedicated(ir):
        if d.sid not in out:
            continue
        svc = dict(out[d.sid])
        svc["environment"] = {**svc.get("environment", {}), **_tool_env(d)}
        files = list(svc.get("env_file", []))
        if f"secrets/{d.sid}.env" not in files:
            files.append(f"secrets/{d.sid}.env")
        svc["env_file"] = files
        svc["depends_on"] = {**svc.get("depends_on", {}), f"{d.sid}-db": {"condition": "service_healthy"}}
        out[d.sid] = svc
        out[f"{d.sid}-db"] = {
            "image": DB_IMAGE, "restart": "unless-stopped",
            "environment": {"POSTGRES_USER": d.name, "POSTGRES_DB": d.name},
            "env_file": [f"secrets/{d.sid}-db.env"], "volumes": [f"{d.sid}-db-data:/var/lib/postgresql/data"],
            "healthcheck": {"test": ["CMD-SHELL", 'pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"'],
                            "interval": "10s", "timeout": "5s", "retries": 10}}
    return out


# ------------------------------------------------------------------ Kubernetes
def _namespace(d: ToolDb) -> str:
    from .entree import namespace_of
    return namespace_of(d.tool, d.brick)


def _connection(ir: IR, d: ToolDb) -> tuple[str, str]:
    """(hôte du service, Secret qui porte « username » et « password »)."""
    if ir.has("cloudnative-pg"):
        return f"{d.sid}-pg-rw", f"{d.sid}-pg-app"
    return f"{d.sid}-db", f"{d.sid}-db"


def kube_files(ir: IR) -> dict[str, str]:
    if not kube_target(ir):
        return {}
    out = {}
    for d in dedicated(ir):
        ns = _namespace(d)
        if ir.has("cloudnative-pg"):
            docs = [{"apiVersion": "postgresql.cnpg.io/v1", "kind": "Cluster",
                     "metadata": {"name": f"{d.sid}-pg", "namespace": ns},
                     "spec": {"instances": 1, "storage": {"size": "5Gi"},
                              "bootstrap": {"initdb": {"database": d.name, "owner": d.name}}}}]
        else:
            from ..databases import ENGINES, Database
            from .data import statefulset_docs
            db = Database(ir.catalog["postgresql"], ENGINES["postgresql"], "self-hosted",
                          {"database": d.name, "user": d.name, "version": "17"})
            docs = statefulset_docs(db, f"{d.sid}-db", DB_IMAGE, "5Gi", {"app": f"{d.sid}-db"})
            for doc in docs:
                doc["metadata"]["namespace"] = ns
        out[f"platform/db-{d.sid}.yaml"] = dump_yaml_docs(docs)
    if out:
        ir.notes.append("Bases dédiées : une base PostgreSQL par outil dans platform/db-<instance>.yaml (Cluster "
                        "CloudNativePG avec l'opérateur, sinon StatefulSet). Les réglages Helm qui branchent l'outil "
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
    if not ir.has("cloudnative-pg"):   # sans l'opérateur : le Secret est tiré une fois
        pre += [f"if ! kubectl -n {ns} get secret {secret} >/dev/null 2>&1; then  # mot de passe tiré une fois",
                f"  kubectl -n {ns} create secret generic {secret} --from-literal=username={d.name} "
                '--from-literal=password="$(openssl rand -hex 24)"', "fi"]
    pre.append(f'kubectl apply -f "$(dirname "$0")/db-{d.sid}.yaml"')
    return pre, _helm_args(tool, d, host, secret)


def _helm_args(tool: str, d: ToolDb, host: str, secret: str) -> str:
    if tool == "gitea":
        env = "gitea.additionalConfigFromEnvs[0]"
        return (" --set postgresql-ha.enabled=false --set postgresql.enabled=false"
                " --set gitea.config.database.DB_TYPE=postgres"
                f" --set gitea.config.database.HOST={host}:5432 --set gitea.config.database.NAME={d.name}"
                f" --set gitea.config.database.USER={d.name} --set '{env}.name=GITEA__DATABASE__PASSWD'"
                f" --set '{env}.valueFrom.secretKeyRef.name={secret}' --set '{env}.valueFrom.secretKeyRef.key=password'")
    if tool == "sonarqube":
        return (" --set postgresql.enabled=false --set jdbcOverwrite.enable=true"
                f" --set jdbcOverwrite.jdbcUrl=jdbc:postgresql://{host}:5432/{d.name}"
                f" --set jdbcOverwrite.jdbcUsername={d.name} --set jdbcOverwrite.jdbcSecretName={secret}"
                " --set jdbcOverwrite.jdbcSecretPasswordKey=password")
    env = "envValueFrom.GF_DATABASE_PASSWORD.secretKeyRef"
    return (" --set 'grafana\\.ini.database.type=postgres'"
            f" --set 'grafana\\.ini.database.host={host}:5432' --set 'grafana\\.ini.database.name={d.name}'"
            f" --set 'grafana\\.ini.database.user={d.name}' --set '{env}.name={secret}' --set '{env}.key=password'")
