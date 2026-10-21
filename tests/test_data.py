# SPDX-License-Identifier: Apache-2.0
"""Lot 0.8 : étape « Données » — bases autogérées, opérateur, bases managées, migrations."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import minihelm
import pytest
import yaml

from devops_builder import appscan
from devops_builder.catalog import default_catalog
from devops_builder.compat import incompatibility
from devops_builder.databases import DATABASE_TOOLS, MANAGED, databases
from devops_builder.generators import generate, render
from devops_builder.model import STAGE_IDS, Project, env_preset
from devops_builder.ports import port_plan
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, answers_from_profile, build_starter, database_brick

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)


def project(target: str, *tools: str, envs: str = "staging-prod", **params) -> Project:
    p = Project(name="Boutique", target=target, environments=env_preset(envs))
    p.app.image_name, p.app.port = "shop", 8000
    for t in tools:
        p.add(t, CATALOG[t].stage, **params.get(t.replace("-", "_"), {}))
    return p


COMPOSE = ("gitlab", "gitlab-ci", "buildkit", "docker-compose", "traefik")
K3S_HELM = ("github", "github-actions", "buildkit", "ghcr", "k3s", "helm")
K3S_KUST = ("gitlab", "gitlab-ci", "buildkit", "k3s", "kustomize")


def files_of(p: Project) -> dict[str, str]:
    return generate(p, CATALOG, ENGINE, allow_blocking=True).files


# ------------------------------------------------------------------ catalogue et format
def test_etape_donnees_entre_infrastructure_et_deploiement():
    assert STAGE_IDS.index("data") == STAGE_IDS.index("infrastructure") + 1
    assert STAGE_IDS.index("data") + 1 == STAGE_IDS.index("deploy")
    for tid in DATABASE_TOOLS + ("db-migrations",):
        assert CATALOG[tid].stage == "data" and CATALOG[tid].curated


def test_fournisseurs_declarent_leur_base_managee():
    for prov, svc in {"aws": "aws-rds", "gcp": "cloud-sql", "azure": "azure-database",
                      "scaleway": "scaleway-rdb", "ovhcloud": "ovh-databases"}.items():
        assert CATALOG[prov].services["database"] == svc
        assert CATALOG[svc].provider == prov


def test_bases_du_landscape_rangees_en_donnees_sans_casser_les_anciens_projets():
    lsc = [t for t in CATALOG.tools.values() if not t.curated and t.landscape
           and t.landscape.subcategory == "Database"]
    assert lsc and all(t.stage == "data" and "platform" in t.extra_stages for t in lsc)
    old = Project(target="kubernetes")
    old.add(lsc[0].id, "platform")  # posée en Plateforme par une version 0.7
    assert "R25" not in {d.rule_id for d in ENGINE.evaluate(old)}
    # Les fiches curées remplacent les entrées brutes du Landscape
    assert CATALOG.get("lsc-cloudnativepg").id == "cloudnative-pg"


def test_etape_vide_omise_du_fichier_projet():
    p = project("docker-host", *COMPOSE)
    assert "data:" not in p.to_yaml()
    p.add("postgresql", "data")
    text = p.to_yaml()
    assert "  data:\n" in text
    again = Project.from_yaml(text)
    assert [b.tool for b in again.stages["data"]] == ["postgresql"]


# ------------------------------------------------------------------ Compose
def compose_project(envs: str = "dev-recette-prod") -> Project:
    return project("docker-host", *COMPOSE, "postgresql", "valkey", "db-migrations", envs=envs,
                   db_migrations={"command": "alembic upgrade head"})


def test_compose_base_interne_avec_volume_sante_et_migrations():
    f = files_of(compose_project())
    doc = yaml.safe_load(f["deploy/docker-compose.yml"])
    pg, app, migrate = doc["services"]["postgresql"], doc["services"]["shop"], doc["services"]["migrate"]
    assert pg["image"] == "postgres:18" and "ports" not in pg
    assert pg["volumes"] == ["postgresql-data:/var/lib/postgresql"]  # postgres 18+ : volume sur le parent de PGDATA
    assert pg["environment"] == {"POSTGRES_USER": "app", "POSTGRES_DB": "app"}
    assert pg["env_file"] == ["secrets/postgresql.env"] and "pg_isready" in pg["healthcheck"]["test"][1]
    assert app["env_file"] == ["secrets/app.env"]
    assert app["depends_on"]["migrate"] == {"condition": "service_completed_successfully"}
    assert app["depends_on"]["postgresql"] == {"condition": "service_healthy"}
    assert migrate["image"] == app["image"] and migrate["command"] == ["sh", "-c", "alembic upgrade head"]
    # traefik-letsencrypt : certificats de Traefik (HTTPS réel depuis la 0.17)
    assert set(doc["volumes"]) == {"postgresql-data", "valkey-data", "traefik-letsencrypt"}
    assert "&id" not in f["deploy/docker-compose.yml"]
    assert "$${VALKEY_PASSWORD}" in doc["services"]["valkey"]["command"][2]


def test_postgres_17_garde_l_ancien_point_de_montage():
    p = project("docker-host", *COMPOSE, "postgresql", postgresql={"version": "17"})
    doc = yaml.safe_load(files_of(p)["deploy/docker-compose.yml"])
    assert doc["services"]["postgresql"]["volumes"] == ["postgresql-data:/var/lib/postgresql/data"]


def test_script_de_secrets_ecrit_des_fichiers_prives(tmp_path):
    f = files_of(compose_project("prod"))
    script = tmp_path / "secrets.sh"
    script.write_text(f["deploy/secrets.sh"], encoding="utf-8")
    env = {**os.environ, "POSTGRESQL_PASSWORD": "s3cret-Pw", "VALKEY_PASSWORD": "cache.Pw"}
    subprocess.run(["sh", str(script), str(tmp_path / "out")], check=True, env=env, capture_output=True)
    app = (tmp_path / "out" / "app.env").read_text()
    assert "DATABASE_URL=postgresql://app:s3cret-Pw@postgresql:5432/app" in app
    assert "REDIS_URL=redis://:cache.Pw@valkey:6379/0" in app
    assert (tmp_path / "out" / "postgresql.env").read_text() == "POSTGRES_PASSWORD=s3cret-Pw\n"
    assert stat.S_IMODE((tmp_path / "out" / "app.env").stat().st_mode) == 0o600
    bad = subprocess.run(["sh", str(script), str(tmp_path / "bad")], env={**env, "POSTGRESQL_PASSWORD": "a@b"},
                         capture_output=True, text=True)
    assert bad.returncode != 0 and "caractères autorisés" in bad.stderr
    missing = subprocess.run(["sh", str(script), str(tmp_path / "x")], env={k: v for k, v in env.items()
                             if k != "VALKEY_PASSWORD"}, capture_output=True, text=True)
    assert missing.returncode != 0 and "VALKEY_PASSWORD" in missing.stderr


def test_deploiement_ssh_transmet_les_secrets_par_environnement():
    f = files_of(compose_project())
    ci = f[".gitlab-ci.yml"]
    assert 'POSTGRESQL_PASSWORD="$POSTGRESQL_PASSWORD_RECETTE" VALKEY_PASSWORD="$VALKEY_PASSWORD_RECETTE" ' \
           "sh deploy/secrets.sh .secrets" in ci
    assert 'tar -C .secrets -cf - . | ssh "$DEPLOY_HOST_RECETTE"' in ci
    assert "rm -rf .secrets" in ci and 'scp scripts/db-backup.sh "$DEPLOY_HOST_PRODUCTION:/opt/shop/db-backup.sh"' in ci
    report = f["PIPELINE.md"]
    for var in ("POSTGRESQL_PASSWORD_DEV", "POSTGRESQL_PASSWORD_RECETTE", "VALKEY_PASSWORD_PRODUCTION"):
        assert f"| `{var}` | oui | à déclarer |" in report
    assert "## Données" in report and "`DATABASE_URL`" in report and "`REDIS_URL`" in report


def test_ansible_copie_les_secrets_et_planifie_la_sauvegarde():
    p = project("vm", "gitlab", "gitlab-ci", "buildkit", "ansible", "docker-compose", "mariadb", envs="prod")
    f = files_of(p)
    tasks = yaml.safe_load(f["ansible/deploy.yml"])[0]["tasks"]
    names = [t["name"] for t in tasks]
    assert names.index("Copier les secrets des bases de données") < names.index("Démarrer les services")
    secret = next(t for t in tasks if t["name"] == "Copier les secrets des bases de données")
    assert secret["no_log"] is True and secret["ansible.builtin.copy"]["mode"] == "0600"
    assert any("ansible.builtin.cron" in t for t in tasks)
    assert "sh deploy/secrets.sh .secrets" in f[".gitlab-ci.yml"]
    assert "mariadb-dump" in f["scripts/db-backup.sh"]


def test_scripts_shell_valides():
    f = files_of(compose_project())
    for rel in ("deploy/secrets.sh", "scripts/db-backup.sh"):
        assert subprocess.run(["sh", "-n"], input=f[rel], text=True).returncode == 0, rel
        if shutil.which("shellcheck"):
            r = subprocess.run(["shellcheck", "-S", "warning", "-s", "sh", "-"], input=f[rel], text=True,
                               capture_output=True)
            assert r.returncode == 0, r.stdout


# ------------------------------------------------------------------ Kubernetes
def chart_docs(f: dict[str, str], env: str | None = None, **sets) -> list[dict]:
    values = yaml.safe_load(f["charts/shop/values.yaml"])
    if env:
        values = minihelm.merge(values, yaml.safe_load(f[f"charts/shop/values-{env}.yaml"]))
    for path, value in sets.items():
        values = minihelm.set_path(values, path.replace("__", "."), value)
    return minihelm.render_chart(f, "charts/shop", values, release="shop-staging")


def test_helm_statefulset_secret_et_url_de_l_application():
    f = files_of(project("kubernetes", *K3S_HELM, "postgresql", "db-migrations",
                         db_migrations={"command": "alembic upgrade head"}))
    with pytest.raises(minihelm.RenderError, match="mot de passe de PostgreSQL"):
        chart_docs(f, "staging")
    docs = chart_docs(f, "staging", database__postgresql__password="pw")
    kinds = {(d["kind"], d["metadata"]["name"]) for d in docs}
    assert {("Secret", "shop-staging-postgresql"), ("StatefulSet", "shop-staging-postgresql"),
            ("Service", "shop-staging-postgresql"), ("Deployment", "shop-staging")} <= kinds
    secret = next(d for d in docs if d["kind"] == "Secret")
    assert secret["stringData"]["url"] == "postgresql://app:pw@shop-staging-postgresql:5432/app"
    pod = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]
    env = pod["containers"][0]["env"]
    assert env == [{"name": "DATABASE_URL", "valueFrom": {"secretKeyRef": {"name": "shop-staging-postgresql",
                                                                           "key": "url"}}}]
    assert pod["initContainers"][0]["command"] == ["sh", "-c", "alembic upgrade head"]
    assert pod["initContainers"][0]["image"] == pod["containers"][0]["image"]
    sts = next(d for d in docs if d["kind"] == "StatefulSet")
    assert sts["spec"]["volumeClaimTemplates"][0]["spec"]["resources"]["requests"]["storage"] == "10Gi"
    ci = f[".github/workflows/pipeline.yml"]
    assert '--set-string database.postgresql.password="$POSTGRESQL_PASSWORD_STAGING"' in ci


def test_helm_cloudnativepg_sans_mot_de_passe_et_instances_par_environnement():
    f = files_of(project("kubernetes", *K3S_HELM, "cloudnative-pg", envs="dev-staging-prod"))
    prod = minihelm.render_chart(f, "charts/shop", minihelm.merge(
        yaml.safe_load(f["charts/shop/values.yaml"]), yaml.safe_load(f["charts/shop/values-production.yaml"])),
        release="shop")
    cluster = next(d for d in prod if d["kind"] == "Cluster")
    assert cluster["spec"]["instances"] == 3 and cluster["metadata"]["name"] == "shop-pg"
    assert cluster["spec"]["bootstrap"]["initdb"] == {"database": "app", "owner": "app"}
    dev = chart_docs(f, "dev")
    assert next(d for d in dev if d["kind"] == "Cluster")["spec"]["instances"] == 1
    env = next(d for d in prod if d["kind"] == "Deployment")["spec"]["template"]["spec"]["containers"][0]["env"]
    assert env[0]["valueFrom"]["secretKeyRef"] == {"name": "shop-pg-app", "key": "uri"}
    assert "--set-string" not in f[".github/workflows/pipeline.yml"]  # l'opérateur crée le Secret
    assert "cnpg/cloudnative-pg --namespace cnpg-system" in f["platform/install.sh"]
    kind = f["scripts/test-kind.sh"]
    assert "cnpg/cloudnative-pg -n cnpg-system" in kind and "--set database.cloudnative_pg.instances=1" in kind
    assert subprocess.run(["bash", "-n"], input=kind, text=True).returncode == 0


def test_gitops_ne_cree_pas_de_secret_et_le_dit():
    f = files_of(project("kubernetes", *K3S_HELM, "argo-cd", "valkey"))
    values = yaml.safe_load(f["charts/shop/values.yaml"])
    assert values["database"]["valkey"]["createSecret"] is False
    docs = minihelm.render_chart(f, "charts/shop", values, release="shop")
    assert not [d for d in docs if d["kind"] == "Secret"]
    assert "External Secrets ou SOPS" in f["PIPELINE.md"]


def kustomize_build(root: Path, overlay: str) -> list[dict]:
    exe = shutil.which("kustomize")
    if exe:
        out = subprocess.run([exe, "build", str(root / overlay)], capture_output=True, text=True, check=True).stdout
    elif shutil.which("kubectl"):
        out = subprocess.run(["kubectl", "kustomize", str(root / overlay)], capture_output=True, text=True,
                             check=True).stdout
    else:
        pytest.skip("kustomize absent")
    return [d for d in yaml.safe_load_all(out) if d]


def test_kustomize_bases_patch_d_instances_et_secrets_crees_par_la_ci(tmp_path):
    p = project("kubernetes", *K3S_KUST, "cloudnative-pg", "valkey")
    result = generate(p, CATALOG, ENGINE, allow_blocking=True)
    result.write(tmp_path)
    prod = kustomize_build(tmp_path, "deploy/kustomize/overlays/production")
    staging = kustomize_build(tmp_path, "deploy/kustomize/overlays/staging")
    pick = lambda docs, kind: next(d for d in docs if d["kind"] == kind)  # noqa: E731
    assert pick(prod, "Cluster")["spec"]["instances"] == 3
    assert pick(staging, "Cluster")["spec"]["instances"] == 1
    assert pick(staging, "StatefulSet")["metadata"]["namespace"] == "shop-staging"
    ci = result.files[".gitlab-ci.yml"]
    assert ('kubectl -n shop-staging create secret generic shop-valkey --from-literal=password="$VALKEY_PASSWORD_STAGING" '
            '--from-literal=url="redis://:$VALKEY_PASSWORD_STAGING@shop-valkey:6379/0"') in " ".join(ci.split())


def test_deux_bases_relationnelles_gardent_des_variables_distinctes():
    p = project("docker-host", *COMPOSE, "postgresql", "mariadb")
    dbs = databases(p, CATALOG)
    assert [d.url_var for d in dbs] == ["DATABASE_URL", "MARIADB_URL"]
    assert "R42" in {d.rule_id for d in ENGINE.evaluate(p)}


# ------------------------------------------------------------------ bases managées
MANAGED_CASES = {
    "aws-rds": (("aws", "ecr", "eks", "helm", "opentofu", "s3"), {"eks": {"cluster_name": "shop"},
                                                                  "s3": {"bucket": "shop-tfstate"}}),
    "cloud-sql": (("gcp", "artifact-registry", "gke", "helm", "terraform"),
                  {"gke": {"cluster_name": "shop"}, "gcp": {"project_id": "shop-prod-1"}}),
    "azure-database": (("azure", "acr", "aks", "kustomize", "terraform"),
                       {"acr": {"registry_name": "shopregistry"}, "aks": {"cluster_name": "shop"},
                        "azure_database": {"engine": "mysql"}}),
    "scaleway-rdb": (("scaleway", "scaleway-registry", "kapsule", "helm", "opentofu"), {"kapsule": {"cluster_name": "shop"}}),
    "ovh-databases": (("ovhcloud", "harbor", "ovh-mks", "helm", "opentofu"),
                      {"ovh_mks": {"cluster_name": "shop"}, "ovhcloud": {"service_name": "0" * 32},
                       "harbor": {"url": "registry.shop.fr"}}),
}
RESOURCES = {"aws-rds": "aws_db_instance", "cloud-sql": "google_sql_database_instance",
             "azure-database": "azurerm_mysql_flexible_server", "scaleway-rdb": "scaleway_rdb_instance",
             "ovh-databases": "ovh_cloud_project_database"}


@pytest.mark.parametrize("tool", [t for t in MANAGED if t in MANAGED_CASES])
def test_base_managee_une_instance_par_environnement(tool, tmp_path):
    extra, params = MANAGED_CASES[tool]
    p = project("kubernetes-managed", "gitlab", "gitlab-ci", "buildkit", *extra, tool, **params)
    result = generate(p, CATALOG, ENGINE, allow_blocking=True)
    blocking = [d.message for d in RuleEngine.blocking(result.diagnostics)]
    assert not blocking, blocking
    main = result.files["infra/terraform/main.tf"]
    labels = re.findall(rf'resource "{RESOURCES[tool]}" "(\w+)"', main)
    assert labels == ["db_staging", "db_production"]
    assert "infra/terraform/outputs.tf" in result.files
    assert ('random = {' in result.files["infra/terraform/versions.tf"]) == (tool in ("cloud-sql", "azure-database",
                                                                                     "scaleway-rdb"))
    assert tool not in [t.id for t in result.ir.unsupported]
    assert "| `DATABASE_URL_STAGING` | oui | à déclarer |" in result.files["PIPELINE.md"]
    if shutil.which("tofu"):
        result.write(tmp_path)
        fmt = subprocess.run(["tofu", "fmt", "-check", "-diff", "infra/terraform"], cwd=tmp_path,
                             capture_output=True, text=True)
        assert fmt.returncode == 0, fmt.stdout


def test_rds_production_protegee_et_haute_disponibilite():
    extra, params = MANAGED_CASES["aws-rds"]
    p = project("kubernetes-managed", "github", "github-actions", "buildkit", *extra, "aws-rds", **params)
    main = files_of(p)["infra/terraform/main.tf"]
    prod = main[main.index('"db_production"'):]
    staging = main[main.index('"db_staging"'):main.index('"db_production"')]
    assert 'identifier                  = "shop"' in prod and "multi_az                    = true" in prod
    assert "deletion_protection         = true" in prod and 'final_snapshot_identifier   = "shop-final"' in prod
    assert 'identifier                  = "shop-staging"' in staging and "skip_final_snapshot         = true" in staging
    assert "manage_master_user_password = true" in main and 'variable "db_subnet_group"' in files_of(p)[
        "infra/terraform/variables.tf"]


# ------------------------------------------------------------------ ports, règles, compat
def test_plan_des_ports_liste_les_bases_sans_les_publier():
    plan = port_plan(compose_project("prod"), CATALOG)
    pg = next(e for e in plan if e.component_id == "postgresql")
    assert pg.host_port is None and pg.container_port == 5432 and "non publié" in pg.exposure
    k8s = port_plan(project("kubernetes", *K3S_HELM, "cloudnative-pg"), CATALOG)
    cnpg = next(e for e in k8s if e.component_id == "cloudnative-pg")
    assert "shop-pg-rw" in cnpg.exposure and "cnpg-system" not in cnpg.exposure


def test_regles_de_production_sur_kubernetes():
    p = project("kubernetes", *K3S_HELM, "postgresql", envs="prod")
    found = {d.rule_id: d for d in ENGINE.evaluate(p)}
    assert {"R40", "R41"} <= set(found)
    assert any(a.args.get("tool") == "cloudnative-pg" for a in found["R41"].actions)
    assert any(a.args.get("tool") == "velero" for a in found["R40"].actions)
    # Pas de production, ou Compose : pas d'avertissement
    hors_prod = project("kubernetes", *K3S_HELM, "postgresql", envs="dev-staging-prod")
    hors_prod.environments = hors_prod.environments[:2]
    assert not {"R40", "R41"} & {d.rule_id for d in ENGINE.evaluate(hors_prod)}
    assert not {"R40", "R41"} & {d.rule_id for d in ENGINE.evaluate(compose_project("prod"))}
    with_velero = project("kubernetes", *K3S_HELM, "postgresql", "velero", "minio", envs="prod")
    assert "R40" not in {d.rule_id for d in ENGINE.evaluate(with_velero)}


def test_migrations_sans_base_et_licence_sspl():
    found = {d.rule_id for d in ENGINE.evaluate(project("docker-host", *COMPOSE, "db-migrations"))}
    assert "R29" in found
    mongo = {d.rule_id: d for d in ENGINE.evaluate(project("docker-host", *COMPOSE, "mongodb"))}
    assert "SSPL-1.0" in mongo["R24"].message


def test_palette_ecarte_une_deuxieme_base_du_meme_type():
    p = project("docker-host", *COMPOSE, "postgresql")
    assert incompatibility(CATALOG["mariadb"], p, CATALOG) == "base relationnelle déjà choisie : PostgreSQL"
    assert incompatibility(CATALOG["valkey"], p, CATALOG) is None
    assert incompatibility(CATALOG["aws-rds"], p, CATALOG) is not None  # pas de fournisseur AWS
    k8s = project("docker-host", *COMPOSE)
    assert "Kubernetes" in incompatibility(CATALOG["cloudnative-pg"], k8s, CATALOG)


def test_chaque_base_est_generee_sur_sa_cible():
    cases = [project("docker-host", *COMPOSE, t) for t in ("postgresql", "mariadb", "mysql", "mongodb", "valkey",
                                                          "redis")]
    cases += [project("kubernetes", *K3S_HELM, t) for t in ("postgresql", "mongodb", "cloudnative-pg", "redis")]
    cases += [project("kubernetes", *K3S_KUST, t) for t in ("mysql", "valkey")]
    for p in cases:
        _, ir = render(p, CATALOG)
        assert [t.id for t in ir.unsupported] == [], [b.tool for _, b in p.all_bricks()]


# ------------------------------------------------------------------ analyse et assistant
def tree(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content, encoding="utf-8")
    return root


@pytest.mark.parametrize("files,engines,migrations", [
    ({"requirements.txt": "fastapi\npsycopg[binary]>=3\nredis\nalembic\n", "alembic.ini": ""},
     ["postgresql", "valkey"], "alembic upgrade head"),
    ({"pyproject.toml": '[project]\nname="x"\ndependencies=["django","mysqlclient"]\n', "manage.py": ""},
     ["mysql"], "python manage.py migrate --noinput"),
    ({"package.json": '{"name":"api","dependencies":{"@prisma/client":"5","ioredis":"5"},'
                      '"devDependencies":{"prisma":"5"}}',
      "prisma/schema.prisma": 'datasource db {\n  provider = "postgresql"\n  url = env("DATABASE_URL")\n}\n'},
     ["postgresql", "valkey"], "npx prisma migrate deploy"),
    ({"package.json": '{"name":"api","dependencies":{"mongoose":"8"}}'}, ["mongodb"], None),
    ({"go.mod": "module ex.com/svc\n\nrequire (\n\tgithub.com/jackc/pgx/v5 v5.7.0\n\tgithub.com/pressly/goose/v3 v3.24\n)\n"},
     ["postgresql"], 'goose -dir migrations postgres "$DATABASE_URL" up'),
    ({"pom.xml": "<project><artifactId>svc</artifactId><dependency><artifactId>spring-boot</artifactId></dependency>"
                 "<dependency><artifactId>mariadb-java-client</artifactId></dependency>"
                 "<dependency><artifactId>flyway-core</artifactId></dependency></project>"}, ["mariadb"], None),
    ({"requirements.txt": "flask\n", "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n"},
     ["postgresql"], None),
])
def test_analyse_detecte_bases_et_migrations(tmp_path, files, engines, migrations):
    profile = appscan.scan(tree(tmp_path / "app", files))
    assert profile.databases == engines
    assert profile.migrations == migrations


def test_brique_choisie_selon_l_hebergement():
    assert database_brick("postgresql", project("docker-host", *COMPOSE), CATALOG) == ("postgresql", {})
    assert database_brick("postgresql", project("kubernetes", *K3S_HELM), CATALOG) == ("cloudnative-pg", {})
    aws = project("kubernetes-managed", "aws", "eks", "helm")
    assert database_brick("mysql", aws, CATALOG) == ("aws-rds", {"engine": "mysql"})
    assert database_brick("postgresql", aws, CATALOG) == ("aws-rds", {})
    scw = project("kubernetes-managed", "scaleway", "kapsule", "helm")
    assert database_brick("mariadb", scw, CATALOG) == ("scaleway-rdb", {"engine": "MySQL-8"})
    assert database_brick("mongodb", aws, CATALOG) == ("mongodb", {})
    assert database_brick("redis", aws, CATALOG) == ("valkey", {})


def test_assistant_et_propositions_reprennent_la_base(tmp_path):
    root = tree(tmp_path / "app", {"requirements.txt": "fastapi\nasyncpg\nredis\nalembic\n",
                                   "Dockerfile": "FROM python:3.12\nEXPOSE 8000\n"})
    profile = appscan.scan(root)
    a, taken = answers_from_profile(profile, CATALOG, StarterAnswers(hosting="kubernetes"))
    assert (a.database, a.cache, a.migrations) == ("postgresql", True, "alembic upgrade head")
    assert any("PostgreSQL" in t for t in taken)
    p = build_starter(a, CATALOG)
    assert {"cloudnative-pg", "valkey", "db-migrations"} <= p.tool_ids()
    assert p.bricks_for("db-migrations")[0].params == {"command": "alembic upgrade head"}
    assert not RuleEngine.blocking(ENGINE.evaluate(p))
    existing = project("docker-host", *COMPOSE)
    offers = dict(appscan.proposed_bricks(profile, existing, CATALOG))
    assert {"postgresql", "valkey", "db-migrations"} <= set(offers)
    assert appscan.proposed_params(profile, "db-migrations", existing, CATALOG) == {"command": "alembic upgrade head"}
    existing.add("mariadb", "data")
    assert "postgresql" not in dict(appscan.proposed_bricks(profile, existing, CATALOG))


@pytest.mark.parametrize("hosting,cloud", [("docker-host", None), ("vm", None), ("kubernetes", None),
                                           ("kubernetes-managed", "aws"), ("kubernetes-managed", "gcp"),
                                           ("kubernetes-managed", "azure"), ("kubernetes-managed", "scaleway"),
                                           ("kubernetes-managed", "ovhcloud"), ("kubernetes-managed", "outscale"),
                                           ("serverless", "gcp")])
@pytest.mark.parametrize("database", ["postgresql", "mysql", "mariadb", "mongodb"])
def test_assistant_avec_base_jamais_bloquant(hosting, cloud, database):
    a = StarterAnswers(hosting=hosting, cloud=cloud, envs="dev-staging-prod", database=database, cache=True,
                       migrations="./migrate")
    p = build_starter(a, CATALOG)
    assert not RuleEngine.blocking(ENGINE.evaluate(p)), [d.message for d in ENGINE.evaluate(p)]
    assert any(t in p.tool_ids() for t in DATABASE_TOOLS)
