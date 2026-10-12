"""Analyse du dossier d'une application : ce qu'il faut savoir pour lui construire un pipeline.

Lecture seule et sans exécuter de code : les fichiers sont lus tels quels (pas de `git`,
pas d'installation de dépendances). Chaque détection garde sa preuve (« Python : pyproject.toml »)
pour que l'utilisateur sache d'où vient la proposition.
"""

from __future__ import annotations

import configparser
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "target", "vendor",
             ".idea", ".vscode", ".terraform", ".tox", ".mypy_cache", ".pytest_cache", "bin", "obj", ".next"}
MAX_DEPTH = 4
MAX_FILES = 20000

# Port d'écoute par défaut des cadres applicatifs courants
FRAMEWORK_PORTS = {"fastapi": 8000, "uvicorn": 8000, "django": 8000, "flask": 5000, "streamlit": 8501,
                   "express": 3000, "next": 3000, "@nestjs/core": 3000, "nuxt": 3000, "fastify": 3000,
                   "spring-boot": 8080, "quarkus": 8080, "aspnet": 8080, "gin": 8080, "echo": 8080}
LANGUAGE_PORTS = {"python": 8000, "node": 3000, "java": 8080, "go": 8080, "dotnet": 8080}
CI_FILES = [(".gitlab-ci.yml", "gitlab-ci"), (".github/workflows", "github-actions"), (".gitea/workflows", "gitea-actions"),
            ("Jenkinsfile", "jenkins"), (".woodpecker.yml", "woodpecker"), (".woodpecker", "woodpecker"),
            ("azure-pipelines.yml", "azure-pipelines"), ("buildspec.yml", "aws-codebuild"),
            ("cloudbuild.yaml", "google-cloud-build"), (".tekton", "tekton")]
# Pilotes et bibliothèques qui trahissent une base : (moteur, motif cherché dans les dépendances)
DB_DRIVERS: dict[str, list[tuple[str, str]]] = {
    "python": [("postgresql", r"\b(psycopg2?(-binary)?|asyncpg|pg8000)\b"), ("mysql", r"\b(mysqlclient|pymysql|aiomysql|mysql-connector-python)\b"),
               ("mariadb", r"^\s*\"?mariadb\b"), ("mongodb", r"\b(pymongo|motor|mongoengine|beanie)\b"),
               ("valkey", r"\b(redis|valkey|django-redis|celery\[redis\])\b")],
    "node": [("postgresql", r'"(pg|postgres|pg-promise)"'), ("mysql", r'"(mysql2?)"'), ("mariadb", r'"mariadb"'),
             ("mongodb", r'"(mongodb|mongoose)"'), ("valkey", r'"(redis|ioredis|iovalkey|@valkey/valkey-glide)"')],
    "java": [("postgresql", r"<artifactId>postgresql</artifactId>|org\.postgresql"),
             ("mysql", r"mysql-connector-j|mysql-connector-java"), ("mariadb", r"mariadb-java-client"),
             ("mongodb", r"mongodb-driver|spring-boot-starter-data-mongodb"),
             ("valkey", r"jedis|lettuce-core|spring-boot-starter-data-redis")],
    "go": [("postgresql", r"jackc/pgx|lib/pq"), ("mysql", r"go-sql-driver/mysql"),
           ("mongodb", r"go\.mongodb\.org/mongo-driver"), ("valkey", r"redis/go-redis|go-redis/redis|valkey-io/valkey-go")],
    "dotnet": [("postgresql", r"Npgsql"), ("mysql", r"MySql\.Data|MySqlConnector|Pomelo\.EntityFrameworkCore\.MySql"),
               ("mongodb", r"MongoDB\.Driver"), ("valkey", r"StackExchange\.Redis")],
}
COMPOSE_DB_IMAGES = [("postgresql", r"image:\s*['\"]?(\S*/)?postgres(ql)?[:'\"\s]"), ("mariadb", r"image:\s*['\"]?(\S*/)?mariadb[:'\"\s]"),
                     ("mysql", r"image:\s*['\"]?(\S*/)?mysql[:'\"\s]"), ("mongodb", r"image:\s*['\"]?(\S*/)?mongo(db)?[:'\"\s]"),
                     ("valkey", r"image:\s*['\"]?(\S*/)?(valkey|redis)[:'\"\s]")]
AWS_SDKS = {"python": r"\b(boto3|aioboto3|botocore)\b", "node": r'"@aws-sdk/|"aws-sdk"',
            "java": r"software\.amazon\.awssdk|aws-java-sdk", "go": r"aws/aws-sdk-go", "dotnet": r"AWSSDK\."}
EMULATORS = [("floci", r"floci/floci|testcontainers-floci|@floci/testcontainers|io\.floci"),
             ("localstack", r"localstack")]
FORGE_HOSTS = [("github.com", "github"), ("gitlab", "gitlab"), ("bitbucket.org", "bitbucket"),
               ("dev.azure.com", "azure-repos"), ("visualstudio.com", "azure-repos"), ("codeberg.org", "gitea"),
               ("gitea", "gitea")]


@dataclass
class AppProfile:
    path: Path
    name: str = ""
    image_name: str = ""
    language: str = "other"
    framework: str = ""
    port: int | None = None
    port_source: str = ""
    dockerfile: bool = False
    base_image: str = ""
    compose: bool = False
    ci: str | None = None
    forge: str | None = None
    remote: str = ""
    helm: bool = False
    kustomize: bool = False
    k8s_manifests: bool = False
    iac: str | None = None
    dependencies: str | None = None
    has_tests: bool = False
    databases: list[str] = field(default_factory=list)   # moteurs détectés, le principal d'abord
    aws_sdk: bool = False                                 # l'application appelle des API AWS
    aws_emulator: str | None = None                      # émulateur déjà utilisé : floci ou localstack
    migrations: str | None = None                        # commande de migration de schéma
    # variable et format de connexion lus par l'application, par famille (sql, document, key-value)
    connections: dict[str, dict] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)

    @property
    def hosting_hint(self) -> str | None:
        if self.helm or self.kustomize or self.k8s_manifests:
            return "kubernetes"
        if self.compose:
            return "docker-host"
        return None

    def summary(self) -> list[str]:
        """Lignes lisibles : ce qui a été trouvé, avec sa preuve."""
        return list(self.evidence)


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "mon-app")[:40].rstrip("-")


def _files(root: Path) -> list[Path]:
    out: list[Path] = []
    stack = [(root, 0)]
    while stack and len(out) < MAX_FILES:
        folder, depth = stack.pop()
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in SKIP_DIRS and depth < MAX_DEPTH and not entry.is_symlink():
                    stack.append((entry, depth + 1))
            elif entry.is_file():
                out.append(entry)
    return out


def _read(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def scan(path: str | Path) -> AppProfile:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"{root} n'est pas un dossier.")
    p = AppProfile(path=root, name=root.name)
    files = _files(root)
    names = {f.name for f in files}
    top = {f.name: f for f in files if f.parent == root}
    _language(root, p, top, files)
    _dockerfile(root, p, files)
    _deploy(root, p, files, names)
    _ci_and_forge(root, p)
    _iac(root, p, files)
    _databases(root, p, files, top)
    if any(n in names for n in ("renovate.json", "renovate.json5", ".renovaterc")):
        p.dependencies = "renovate"
        p.evidence.append("Renovate : configuration présente")
    elif (root / ".github" / "dependabot.yml").exists():
        p.dependencies = "dependabot"
        p.evidence.append("Dependabot : .github/dependabot.yml")
    if p.port is None and p.framework in FRAMEWORK_PORTS:
        p.port, p.port_source = FRAMEWORK_PORTS[p.framework], f"port par défaut de {p.framework}"
    if p.port is None and p.language in LANGUAGE_PORTS:
        p.port, p.port_source = LANGUAGE_PORTS[p.language], "port usuel du langage"
    if p.port is not None:
        p.evidence.append(f"Port {p.port} : {p.port_source}")
    p.image_name = slug(p.name)
    return p


def _language(root: Path, p: AppProfile, top: dict[str, Path], files: list[Path]) -> None:
    def deps_text(*paths: Path) -> str:
        return "\n".join(_read(x).lower() for x in paths if x)

    if "pyproject.toml" in top or "requirements.txt" in top or "setup.py" in top or "Pipfile" in top:
        p.language = "python"
        proof = next(n for n in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile") if n in top)
        if "pyproject.toml" in top:
            try:
                data = tomllib.loads(_read(top["pyproject.toml"]))
                p.name = data.get("project", {}).get("name") or data.get("tool", {}).get("poetry", {}).get("name") or p.name
            except tomllib.TOMLDecodeError:
                pass
        text = deps_text(*(top.get(n) for n in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile")))
        p.framework = next((f for f in ("fastapi", "django", "flask", "streamlit") if re.search(rf"\b{f}\b", text)), "")
        p.has_tests = any(n in top for n in ("pytest.ini", "tox.ini", "conftest.py")) or (root / "tests").is_dir() \
            or "pytest" in text
        p.evidence.append(f"Python : {proof}" + (f", cadre {p.framework}" if p.framework else ""))
    elif "package.json" in top:
        p.language = "node"
        try:
            data = json.loads(_read(top["package.json"]))
        except ValueError:
            data = {}
        p.name = (data.get("name") or p.name).split("/")[-1]
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        p.framework = next((f for f in ("next", "@nestjs/core", "nuxt", "fastify", "express") if f in deps), "")
        test = (data.get("scripts") or {}).get("test", "")
        p.has_tests = bool(test) and "no test specified" not in test
        p.evidence.append("Node.js : package.json" + (f", cadre {p.framework}" if p.framework else ""))
    elif "pom.xml" in top or "build.gradle" in top or "build.gradle.kts" in top:
        p.language = "java"
        proof = next(n for n in ("pom.xml", "build.gradle", "build.gradle.kts") if n in top)
        text = _read(top[proof])
        if "spring-boot" in text:
            p.framework = "spring-boot"
        elif "quarkus" in text:
            p.framework = "quarkus"
        m = re.search(r"<artifactId>([^<]+)</artifactId>", text)
        if proof == "pom.xml" and m:
            p.name = m.group(1)
        p.has_tests = (root / "src" / "test").is_dir()
        p.evidence.append(f"Java : {proof}" + (f", cadre {p.framework}" if p.framework else ""))
    elif "go.mod" in top:
        p.language = "go"
        m = re.search(r"^module\s+(\S+)", _read(top["go.mod"]), re.M)
        if m:
            p.name = m.group(1).rstrip("/").split("/")[-1]
        text = _read(top["go.mod"])
        p.framework = "gin" if "gin-gonic/gin" in text else "echo" if "labstack/echo" in text else ""
        p.has_tests = any(f.name.endswith("_test.go") for f in files)
        p.evidence.append("Go : go.mod" + (f", cadre {p.framework}" if p.framework else ""))
    elif any(f.suffix in (".csproj", ".sln", ".fsproj") for f in files):
        p.language = "dotnet"
        proj = next(f for f in files if f.suffix in (".csproj", ".sln", ".fsproj"))
        p.name = proj.stem
        if "Microsoft.NET.Sdk.Web" in _read(proj):
            p.framework = "aspnet"
        p.has_tests = any("test" in f.stem.lower() for f in files if f.suffix == ".csproj")
        p.evidence.append(f".NET : {_rel(root, proj)}" + (", ASP.NET" if p.framework else ""))
    if p.has_tests:
        p.evidence.append("Tests présents")


def _dockerfile(root: Path, p: AppProfile, files: list[Path]) -> None:
    candidates = [f for f in files if f.name == "Dockerfile" or f.name.startswith("Dockerfile.") or f.name == "Containerfile"]
    if not candidates:
        p.evidence.append("Pas de Dockerfile : l'image peut être construite par Buildpacks")
        return
    docker = min(candidates, key=lambda f: (len(f.relative_to(root).parts), f.name != "Dockerfile"))
    p.dockerfile = True
    text = _read(docker)
    froms = re.findall(r"^\s*FROM\s+(\S+)", text, re.M | re.I)
    p.base_image = froms[-1] if froms else ""
    exposes = re.findall(r"^\s*EXPOSE\s+(\d+)", text, re.M | re.I)
    env_port = re.search(r"^\s*ENV\s+PORT[=\s]+(\d+)", text, re.M | re.I)
    if exposes:
        p.port, p.port_source = int(exposes[-1]), f"EXPOSE de {_rel(root, docker)}"
    elif env_port:
        p.port, p.port_source = int(env_port.group(1)), f"ENV PORT de {_rel(root, docker)}"
    p.evidence.append(f"Dockerfile : {_rel(root, docker)}" + (f" (image de base {p.base_image})" if p.base_image else ""))


def _deploy(root: Path, p: AppProfile, files: list[Path], names: set[str]) -> None:
    chart = next((f for f in files if f.name == "Chart.yaml"), None)
    if chart:
        p.helm = True
        p.evidence.append(f"Chart Helm : {_rel(root, chart.parent)}")
    kust = next((f for f in files if f.name in ("kustomization.yaml", "kustomization.yml")), None)
    if kust:
        p.kustomize = True
        p.evidence.append(f"Kustomize : {_rel(root, kust)}")
    if not (chart or kust):
        for f in files:
            if f.suffix in (".yaml", ".yml") and "kind: Deployment" in _read(f, 20_000) and "apiVersion: apps/v1" in _read(f, 20_000):
                p.k8s_manifests = True
                p.evidence.append(f"Manifeste Kubernetes : {_rel(root, f)}")
                break
    compose = next((f for f in files if f.name in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml")), None)
    if compose:
        p.compose = True
        p.evidence.append(f"Docker Compose : {_rel(root, compose)}")


def _ci_and_forge(root: Path, p: AppProfile) -> None:
    for rel, tool in CI_FILES:
        target = root / rel
        if target.exists() and (target.is_file() or any(target.iterdir())):
            p.ci = tool
            p.evidence.append(f"CI existante : {rel}")
            break
    config = root / ".git" / "config"
    if config.is_file():
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            parser.read_string(_read(config))
        except configparser.Error:
            return
        section = 'remote "origin"' if parser.has_section('remote "origin"') else next(
            (s for s in parser.sections() if s.startswith("remote ")), None)
        if section and parser.has_option(section, "url"):
            p.remote = parser.get(section, "url").strip()
            host = re.sub(r"^[a-z+]+://", "", p.remote).split("@")[-1].split("/")[0].split(":")[0].lower()
            p.forge = next((forge for needle, forge in FORGE_HOSTS if needle in host), None)
            p.evidence.append(f"Dépôt distant : {p.remote}" + (f" (forge {p.forge})" if p.forge else ""))
    if p.forge is None and p.ci in ("gitlab-ci", "github-actions", "gitea-actions", "azure-pipelines"):
        p.forge = {"gitlab-ci": "gitlab", "github-actions": "github", "gitea-actions": "gitea",
                   "azure-pipelines": "azure-repos"}[p.ci]


def _iac(root: Path, p: AppProfile, files: list[Path]) -> None:
    tf = [f for f in files if f.suffix == ".tf"]
    if not tf:
        return
    lock = next((f for f in files if f.name == ".terraform.lock.hcl"), None)
    tofu = (lock and "registry.opentofu.org" in _read(lock)) or any(f.name.endswith(".tofu") for f in files)
    p.iac = "opentofu" if tofu else "terraform"
    folder = _rel(root, tf[0].parent) if tf[0].parent != root else "."
    p.evidence.append(f"{'OpenTofu' if tofu else 'Terraform'} : fichiers .tf dans {folder}")


def _dependency_text(root: Path, p: AppProfile, top: dict[str, Path], files: list[Path]) -> str:
    names = {"python": ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "poetry.lock"),
             "node": ("package.json",), "java": ("pom.xml", "build.gradle", "build.gradle.kts"), "go": ("go.mod",)}
    if p.language == "dotnet":
        return "\n".join(_read(f) for f in files if f.suffix in (".csproj", ".fsproj"))
    text = "\n".join(_read(top[n]) for n in names.get(p.language, ()) if n in top)
    if p.language == "python":
        text += "\n".join(_read(f) for f in files if f.parent == root and re.match(r"requirements.*\.txt$", f.name))
    return text


def _databases(root: Path, p: AppProfile, files: list[Path], top: dict[str, Path]) -> None:
    """Bases utilisées par l'application (pilotes, schéma Prisma, Compose) et ses migrations."""
    deps = _dependency_text(root, p, top, files)
    found: list[tuple[str, str]] = []

    def hit(engine: str, proof: str) -> None:
        if engine not in [e for e, _ in found]:
            found.append((engine, proof))

    prisma = next((f for f in files if f.name == "schema.prisma"), None)
    if prisma:
        m = re.search(r'provider\s*=\s*"(postgresql|mysql|mongodb|cockroachdb)"', _read(prisma))
        if m and m.group(1) != "cockroachdb":
            hit({"postgresql": "postgresql", "mysql": "mysql", "mongodb": "mongodb"}[m.group(1)],
                f"schéma Prisma {_rel(root, prisma)}")
    flags = re.M | (re.I if p.language == "python" else 0)
    for engine, pattern in DB_DRIVERS.get(p.language, []):
        if re.search(pattern, deps, flags):
            hit(engine, "pilote dans les dépendances")
    compose = next((f for f in files if f.name in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml")), None)
    if compose:
        text = _read(compose)
        for engine, pattern in COMPOSE_DB_IMAGES:
            if re.search(pattern, text, re.I):
                hit(engine, f"service de {_rel(root, compose)}")
    found.sort(key=lambda x: x[0] == "valkey")  # la base principale avant le cache
    labels = {"postgresql": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB", "mongodb": "MongoDB",
              "valkey": "Redis / Valkey"}
    for engine, proof in found:
        p.databases.append(engine)
        p.evidence.append(f"Base {labels[engine]} : {proof}")
    _migrations(root, p, files, top, deps, prisma)
    _connections(root, p, files)
    _aws(p, deps, _read(compose) if compose else "")


ENV_READS = re.compile(
    r"""(?:os\.environ\.get|os\.environ|os\.getenv|getenv|os\.Getenv|GetEnvironmentVariable|System\.getenv|"""
    r"""env(?:\.\w+)?|config)\s*[\(\[]\s*["']([A-Z][A-Z0-9_]{2,})["']"""
    r"""|process\.env\.([A-Z][A-Z0-9_]{2,})|process\.env\[["']([A-Z][A-Z0-9_]{2,})["']\]"""
    r"""|\$\{([A-Z][A-Z0-9_]{2,})(?::[^}]*)?\}""")
SQL_PREFIX = r"(?:[A-Z0-9]+_)*(?:DATABASE|DB|POSTGRES(?:QL)?|PG|MYSQL|MARIADB|SQL)"
FAMILY_URL = {
    "sql": re.compile(rf"^{SQL_PREFIX}(?:_[A-Z0-9]+)*_(?:URL|URI|DSN)$"),
    "document": re.compile(r"^(?:[A-Z0-9]+_)*MONGO(?:DB)?(?:_[A-Z0-9]+)*_(?:URL|URI)$"),
    "key-value": re.compile(r"^(?:[A-Z0-9]+_)*(?:REDIS|VALKEY|CACHE)(?:_[A-Z0-9]+)*_(?:URL|URI)$"),
}
CODE_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".ts", ".go", ".java", ".kt", ".cs", ".rb", ".php", ".properties",
                 ".yml", ".yaml", ".toml", ".env", ".example")


def _connections(root: Path, p: AppProfile, files: list[Path]) -> None:
    """Variable (et format) dans laquelle l'application lit la connexion à chaque base."""
    from .databases import ENGINES
    families = {ENGINES[e].family for e in p.databases if e in ENGINES}
    if not families:
        return
    names: dict[str, int] = {}
    for f in files:
        if not f.name.endswith(CODE_SUFFIXES) or any(part in SKIP_DIRS for part in f.parts):
            continue
        for m in ENV_READS.finditer(_read(f, 100_000)):
            name = next(g for g in m.groups() if g)
            names[name] = names.get(name, 0) + 1
    java = p.framework in ("spring-boot", "quarkus")
    if "sql" in families and java:
        default = "SPRING_DATASOURCE_URL" if p.framework == "spring-boot" else "QUARKUS_DATASOURCE_JDBC_URL"
        var = next((n for n in names if FAMILY_URL["sql"].match(n)), default)
        p.connections["sql"] = {"url_var": var, "url_format": "jdbc"}
        p.evidence.append(f"Connexion JDBC dans {var} ({'Spring Boot' if p.framework == 'spring-boot' else 'Quarkus'})")
    for family in sorted(families - ({"sql"} if java else set())):
        found = sorted((n for n in names if FAMILY_URL[family].match(n)), key=lambda n: (-names[n], len(n)))
        if found:
            p.connections[family] = {"url_var": found[0]}
            p.evidence.append(f"Connexion lue dans {found[0]}")
        elif family == "sql":
            prefix = next((pre for pre in ("DATABASE", "DB", "POSTGRES", "PG", "MYSQL")
                           if f"{pre}_HOST" in names and (f"{pre}_PASSWORD" in names or f"{pre}_PASS" in names)), None)
            if prefix:
                p.connections["sql"] = {"url_var": f"{prefix}_URL", "url_format": "parts"}
                p.evidence.append(f"Connexion lue en variables séparées {prefix}_HOST, {prefix}_PASSWORD…")


def _aws(p: AppProfile, deps: str, compose: str) -> None:
    if re.search(AWS_SDKS.get(p.language, r"$^"), deps, re.I):
        p.aws_sdk = True
        p.evidence.append("SDK AWS dans les dépendances")
    for name, pattern in EMULATORS:
        if re.search(pattern, deps + "\n" + compose, re.I):
            p.aws_emulator = name
            p.evidence.append(f"Émulateur AWS : {'Floci' if name == 'floci' else 'LocalStack'}")
            break


def _migrations(root: Path, p: AppProfile, files: list[Path], top: dict[str, Path], deps: str,
                prisma: Path | None) -> None:
    names = {f.name for f in files}
    found: tuple[str, str] | None = None
    if p.language == "python":
        if "alembic.ini" in names or re.search(r"\balembic\b", deps, re.I):
            found = ("alembic upgrade head", "Alembic")
        elif p.framework == "django" and "manage.py" in top:
            found = ("python manage.py migrate --noinput", "Django")
    elif p.language == "node":
        if prisma and re.search(r'"prisma"', deps):
            found = ("npx prisma migrate deploy", "Prisma")
        elif any(n.startswith("knexfile.") for n in names):
            found = ("npx knex migrate:latest", "Knex")
        elif ".sequelizerc" in names or '"sequelize-cli"' in deps:
            found = ("npx sequelize-cli db:migrate", "Sequelize")
    elif p.language == "go":
        if "pressly/goose" in deps:
            found = ('goose -dir migrations postgres "$DATABASE_URL" up', "goose")
        elif "golang-migrate/migrate" in deps:
            found = ('migrate -path migrations -database "$DATABASE_URL" up', "golang-migrate")
    elif p.language == "java" and re.search(r"flyway-core|liquibase-core", deps):
        tool = "Flyway" if "flyway" in deps else "Liquibase"
        p.evidence.append(f"Migrations {tool} : appliquées par l'application à son démarrage")
        return
    if found:
        p.migrations = found[0]
        p.evidence.append(f"Migrations {found[1]} : {found[0]}")


def to_json(p: AppProfile) -> dict:
    data = {k: v for k, v in p.__dict__.items() if k != "path"}
    data["path"] = str(p.path)
    data["hosting_hint"] = p.hosting_hint
    return data


def proposed_bricks(profile: AppProfile, project, catalog) -> list[tuple[str, str]]:
    """Briques que l'analyse suggère d'ajouter à un projet existant : (identifiant, raison)."""
    from .compat import incompatibility
    from .starter import NATIVE_CI

    roles = {r for _, b in project.all_bricks() if (t := catalog.get(b.tool)) for r in t.roles}
    out: list[tuple[str, str]] = []

    def offer(tool_id: str | None, why: str) -> None:
        tool = catalog.get(tool_id) if tool_id else None
        if tool is None or any(t == tool_id for t, _ in out):
            return
        if incompatibility(tool, project, catalog) is None:
            out.append((tool_id, why))

    if "scm" not in roles and profile.forge:
        offer(profile.forge, "dépôt distant de l'application")
    if "ci" not in roles:
        if profile.ci:
            offer(profile.ci, "CI déjà présente dans le dépôt")
        else:
            forge = profile.forge or next((b.tool for _, b in project.all_bricks()
                                           if (t := catalog.get(b.tool)) and "scm" in t.roles), None)
            if forge in NATIVE_CI:
                offer(NATIVE_CI[forge], "CI native de la forge")
    if "image-build" not in roles:
        offer("buildkit" if profile.dockerfile else "buildpacks",
              "Dockerfile présent" if profile.dockerfile else "pas de Dockerfile : image construite par Buildpacks")
    if profile.has_tests:
        offer("unit-tests", "tests présents dans l'application")
    if profile.helm:
        offer("helm", "chart Helm présent")
    if profile.kustomize:
        offer("kustomize", "configuration Kustomize présente")
    if profile.compose:
        offer("docker-compose", "fichier Compose présent")
    if profile.iac and "iac" not in roles:
        offer(profile.iac, "fichiers .tf présents")
    if profile.dependencies and "dependency-update" not in roles:
        offer(profile.dependencies, "mises à jour de dépendances déjà configurées")
    from .databases import ENGINES
    from .starter import database_brick
    families = {ENGINES[e].family for e in profile.databases if e in ENGINES}
    held = {f for f, role in (("sql", "sql-database"), ("document", "document-database"),
                              ("key-value", "key-value-store")) if role in roles}
    for engine in profile.databases:
        family = ENGINES[engine].family
        if family in held:
            continue
        tool_id, _ = database_brick(engine, project, catalog)
        offer(tool_id, f"{ENGINES[engine].label} utilisé par l'application" if tool_id == engine
              else f"{ENGINES[engine].label} utilisé par l'application, porté par {catalog[tool_id].name}")
        held.add(family)
    if profile.migrations and (families or "database" in roles):
        offer("db-migrations", f"migrations « {profile.migrations} »")
    if profile.aws_emulator == "floci":
        offer("floci", "Floci déjà utilisé par l'application")
    elif profile.aws_emulator == "localstack":
        offer("floci", "LocalStack utilisé : Floci le remplace, libre et sans jeton d'accès")
    elif profile.aws_sdk:
        offer("floci", "SDK AWS : tests des appels AWS sur un émulateur local, sans compte")
    return out


def proposed_params(profile: AppProfile, tool_id: str, project, catalog) -> dict:
    """Paramètres à poser avec une brique proposée (moteur d'une base managée, commande de migration)."""
    from .starter import database_brick
    if tool_id == "db-migrations" and profile.migrations:
        return {"command": profile.migrations}
    from .databases import ENGINES
    for engine in profile.databases:
        tid, params = database_brick(engine, project, catalog)
        if tid == tool_id:
            return {**params, **profile.connections.get(ENGINES[engine].family, {})}
    return {}
