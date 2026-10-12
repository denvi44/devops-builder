# SPDX-License-Identifier: Apache-2.0
"""Bases de données du pipeline : moteurs, briques et informations de connexion.

Trois façons d'avoir une base, chacune avec son contrat de connexion :

* **autogérée** (PostgreSQL, MariaDB, MySQL, MongoDB, Valkey, Redis) : un conteneur à côté de
  l'application (service Compose, ou StatefulSet sur Kubernetes). Le mot de passe est une variable
  CI secrète ; l'application reçoit l'URL de connexion complète (DATABASE_URL, MONGODB_URI ou
  REDIS_URL) par un fichier de secrets (Compose) ou un Secret Kubernetes ;
* **opérateur** (CloudNativePG) : la ressource Cluster crée elle-même le Secret « <cluster>-app »
  dont la clé « uri » donne DATABASE_URL ; aucun mot de passe ne transite par la CI ;
* **managée** (RDS, Cloud SQL, Azure, Scaleway, OVHcloud) : décrite en Terraform, une instance par
  environnement ; l'URL de connexion est une variable CI secrète à renseigner après création.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalog import Catalog
from .model import Environment, Project, Tool

PASSWORD_HINT = "lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion)"


@dataclass(frozen=True)
class Engine:
    id: str
    label: str
    family: str          # sql | document | key-value
    port: int
    image: str
    default_version: str
    url_var: str         # variable lue par l'application
    scheme: str
    data_dir: str
    password_env: str = ""
    user_env: str = ""
    db_env: str = ""
    extra_env: tuple[tuple[str, str], ...] = ()
    url_suffix: str = ""

    def data_path(self, version: str) -> str:
        """Point de montage du volume ; l'image postgres 18+ range ses données sous /var/lib/postgresql."""
        if self.id == "postgresql" and _major(version) < 18:
            return "/var/lib/postgresql/data"
        return self.data_dir


def _major(version: str) -> int:
    head = str(version).split(".")[0].split("-")[0]
    return int(head) if head.isdigit() else 99


ENGINES: dict[str, Engine] = {
    "postgresql": Engine("postgresql", "PostgreSQL", "sql", 5432, "postgres", "18", "DATABASE_URL", "postgresql",
                         "/var/lib/postgresql", "POSTGRES_PASSWORD", "POSTGRES_USER", "POSTGRES_DB"),
    "mariadb": Engine("mariadb", "MariaDB", "sql", 3306, "mariadb", "11.8", "DATABASE_URL", "mysql", "/var/lib/mysql",
                      "MARIADB_PASSWORD", "MARIADB_USER", "MARIADB_DATABASE",
                      (("MARIADB_RANDOM_ROOT_PASSWORD", "1"),)),
    "mysql": Engine("mysql", "MySQL", "sql", 3306, "mysql", "8.4", "DATABASE_URL", "mysql", "/var/lib/mysql",
                    "MYSQL_PASSWORD", "MYSQL_USER", "MYSQL_DATABASE", (("MYSQL_RANDOM_ROOT_PASSWORD", "yes"),)),
    "mongodb": Engine("mongodb", "MongoDB", "document", 27017, "mongo", "8.0", "MONGODB_URI", "mongodb", "/data/db",
                      "MONGO_INITDB_ROOT_PASSWORD", "MONGO_INITDB_ROOT_USERNAME", "MONGO_INITDB_DATABASE",
                      url_suffix="?authSource=admin"),
    "valkey": Engine("valkey", "Valkey", "key-value", 6379, "valkey/valkey", "8", "REDIS_URL", "redis", "/data"),
    "redis": Engine("redis", "Redis", "key-value", 6379, "redis", "8", "REDIS_URL", "redis", "/data"),
}
SELF_HOSTED = tuple(ENGINES)
URL_FORMATS = {"url": "URL (postgresql://, mysql://…)", "jdbc": "JDBC (jdbc:postgresql://…, Spring, Quarkus)",
               "parts": "URL et variables séparées (HOST, PORT, NAME, USER, PASSWORD)"}
JDBC_SCHEMES = {"postgresql": "postgresql", "mysql": "mysql", "mariadb": "mariadb"}
OPERATORS = {"cloudnative-pg": "postgresql"}
MANAGED = ("aws-rds", "cloud-sql", "azure-database", "scaleway-rdb", "ovh-databases")
DATABASE_TOOLS = (*SELF_HOSTED, *OPERATORS, *MANAGED)
MIGRATIONS = "db-migrations"

# Moteur choisi pour une base managée → moteur de référence (port, schéma d'URL)
MANAGED_ENGINES = {"postgres": "postgresql", "postgresql": "postgresql", "mysql": "mysql", "mariadb": "mariadb",
                   "PostgreSQL-15": "postgresql", "PostgreSQL-16": "postgresql", "PostgreSQL-17": "postgresql",
                   "MySQL-8": "mysql"}
# Commande de contrôle de santé, exécutée dans le conteneur de la base
HEALTHCHECKS = {
    "postgresql": 'pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"',
    "mariadb": "healthcheck.sh --connect --innodb_initialized",
    "mysql": "mysqladmin ping -h 127.0.0.1 --silent",
    "mongodb": "mongosh --quiet --eval \"db.adminCommand('ping').ok\"",
    "valkey": 'valkey-cli -a "$${VALKEY_PASSWORD}" --no-auth-warning ping | grep -q PONG',
    "redis": 'redis-cli -a "$${REDIS_PASSWORD}" --no-auth-warning ping | grep -q PONG',
}


@dataclass
class Database:
    """Une base de données posée dans le pipeline."""

    tool: Tool
    engine: Engine
    mode: str                      # self-hosted | operator | managed
    params: dict = field(default_factory=dict)
    alt_url_var: str = ""          # deuxième base du même type : variable propre à la brique

    @property
    def id(self) -> str:
        return self.tool.id

    @property
    def version(self) -> str:
        return str(self.params.get("version") or self.engine.default_version)

    @property
    def image(self) -> str:
        return f"{self.engine.image}:{self.version}"

    @property
    def name(self) -> str:
        return str(self.params.get("database") or "app")

    @property
    def user(self) -> str:
        return str(self.params.get("user") or "app")

    @property
    def url_var(self) -> str:
        """Variable lue par l'application : paramètre de la brique, sinon celle du moteur."""
        return str(self.params.get("url_var") or "") or self.alt_url_var or self.engine.url_var

    @property
    def fmt(self) -> str:
        """Format de connexion : url, jdbc ou parts (URL + variables séparées) ; relationnel seulement."""
        value = str(self.params.get("url_format") or "url")
        if self.engine.family != "sql" or value not in URL_FORMATS:
            return "url"
        if value == "parts" and self.mode == "managed":
            return "url"  # R46 : l'URL d'une base managée vient d'une seule valeur
        return value

    @property
    def parts_prefix(self) -> str:
        return re.sub(r"_(URL|URI|DSN)$", "", self.url_var)

    def parts(self) -> list[tuple[str, str]]:
        """(variable, élément) des variables séparées : host, port, name, user, password."""
        if self.fmt != "parts":
            return []
        pre = self.parts_prefix
        return [(f"{pre}_{suffix}", key) for suffix, key in
                (("HOST", "host"), ("PORT", "port"), ("NAME", "name"), ("USER", "user"), ("PASSWORD", "password"))]

    @property
    def password_var(self) -> str:
        """Variable CI du mot de passe (base autogérée)."""
        return f"{self.id.upper().replace('-', '_')}_PASSWORD"

    @property
    def url_ci_var(self) -> str:
        """Variable CI de l'URL de connexion (base managée) : celle que lit l'application."""
        return self.url_var

    def url(self, host: str, password: str) -> str:
        e = self.engine
        if self.fmt == "jdbc":
            return (f"jdbc:{JDBC_SCHEMES.get(e.id, e.scheme)}://{host}:{e.port}/{self.name}"
                    f"?user={self.user}&password={password}")
        if e.family == "key-value":
            return f"{e.scheme}://:{password}@{host}:{e.port}/0"
        return f"{e.scheme}://{self.user}:{password}@{host}:{e.port}/{self.name}{e.url_suffix}"


def databases(project: Project, catalog: Catalog) -> list[Database]:
    from .params import effective_params
    out: list[Database] = []
    for _, b in project.all_bricks():
        tool = catalog.get(b.tool)
        if tool is None or tool.id not in DATABASE_TOOLS or any(d.id == tool.id for d in out):
            continue
        params = effective_params(tool, b, project)
        if tool.id in ENGINES:
            out.append(Database(tool, ENGINES[tool.id], "self-hosted", params))
        elif tool.id in OPERATORS:
            out.append(Database(tool, ENGINES[OPERATORS[tool.id]], "operator", params))
        else:
            engine = MANAGED_ENGINES.get(str(params.get("engine", "postgres")), "postgresql")
            out.append(Database(tool, ENGINES[engine], "managed", params))
    used: set[str] = set()
    for db in out:
        if db.url_var in used and not db.params.get("url_var"):
            db.alt_url_var = f"{db.id.upper().replace('-', '_')}_URL"
        used.add(db.url_var)
    return out


def env_params(db: Database, project: Project, env: Environment) -> dict:
    from .params import effective_params
    bricks = project.bricks_for(db.id)
    return effective_params(db.tool, bricks[0] if bricks else None, project, env)


def migration_command(project: Project, catalog: Catalog) -> str | None:
    if not project.bricks_for(MIGRATIONS) or MIGRATIONS not in catalog:
        return None
    from .params import effective_params
    params = effective_params(catalog[MIGRATIONS], project.bricks_for(MIGRATIONS)[0], project)
    return str(params.get("command") or "").strip() or None
