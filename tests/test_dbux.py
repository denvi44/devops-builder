# SPDX-License-Identifier: Apache-2.0
"""Lot 0.14 : ergonomie des données — vue Données, format de connexion, poste de développement, restauration,
sauvegardes CloudNativePG."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import minihelm
import pytest
import yaml
from test_data import CATALOG, COMPOSE, ENGINE, K3S_HELM, K3S_KUST, kustomize_build, project

from devops_builder import appscan
from devops_builder.datainfo import infos, rows
from devops_builder.generators import generate
from devops_builder.starter import StarterAnswers, answers_from_profile, build_starter


def files_of(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True).files


def rule_ids(p) -> set[str]:
    return {d.rule_id for d in ENGINE.evaluate(p)}


# ------------------------------------------------------------------ ce que deviennent les bases
def test_badge_et_description_selon_le_mode():
    compose = infos(project("docker-host", *COMPOSE, "postgresql"), CATALOG)["postgresql"]
    assert compose.badge == "Conteneur Compose" and compose.connection == "DATABASE_URL"
    assert compose.secret == "variable CI POSTGRESQL_PASSWORD_<ENV>"
    sts = infos(project("kubernetes", *K3S_HELM, "mariadb"), CATALOG)["mariadb"]
    assert sts.badge == "StatefulSet"
    cnpg = infos(project("kubernetes", *K3S_HELM, "cloudnative-pg"), CATALOG)["cloudnative-pg"]
    assert cnpg.badge == "CloudNativePG" and "créé par l'opérateur" in cnpg.secret
    bao = infos(project("docker-host", *COMPOSE, "postgresql", "openbao",
                        openbao={"address": "https://b.example.com"}), CATALOG)["postgresql"]
    assert bao.secret == "OpenBao, secret/<espace de noms>/postgresql"  # la source réelle, plus « variable CI »


def test_vue_donnees_une_ligne_par_environnement_avec_avertissements():
    p = project("kubernetes", *K3S_HELM, "postgresql", envs="dev-staging-prod",
                postgresql={"storage": "20Gi"})
    lines = rows(p, CATALOG, ENGINE.evaluate(p))
    assert [r.env_id for r in lines] == ["dev", "staging", "production"]
    assert lines[0].size == "20Gi" and lines[0].version == "18"
    prod = lines[-1]
    assert any(w.startswith("R41") for w in prod.warnings) and any(w.startswith("R40") for w in prod.warnings)


def test_vue_donnees_dans_l_interface(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from devops_builder.ui.data import DataDialog
    _ = QApplication.instance() or QApplication([])
    p = project("kubernetes", *K3S_HELM, "postgresql", envs="staging-prod")
    applied = []

    def fix(action):
        applied.append(action)
        from devops_builder.rules import apply_action
        apply_action(p, action, CATALOG)
        return p
    dlg = DataDialog(p, CATALOG, ENGINE, apply_fix=fix, focus_brick=lambda uid: None)
    assert dlg.tree.topLevelItemCount() == 2
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(1))
    assert dlg.fix.isEnabled() and dlg.fix.text().startswith("Corriger : ")
    dlg.fix.click()
    assert len(applied) == 1 and applied[0].op in ("add_brick", "replace_brick")
    dlg.close()


# ------------------------------------------------------------------ variable et format de connexion
def test_format_jdbc_et_variable_spring():
    p = project("docker-host", *COMPOSE, "postgresql",
                postgresql={"url_format": "jdbc", "url_var": "SPRING_DATASOURCE_URL"})
    script = files_of(p)["deploy/secrets.sh"]
    assert "SPRING_DATASOURCE_URL=jdbc:postgresql://postgresql:5432/app?user=app&password=$POSTGRESQL_PASSWORD" in script


def test_variables_separees_compose_et_kubernetes():
    p = project("docker-host", *COMPOSE, "postgresql", postgresql={"url_format": "parts"})
    script = files_of(p)["deploy/secrets.sh"]
    for line in ("DATABASE_HOST=postgresql", "DATABASE_PORT=5432", "DATABASE_NAME=app", "DATABASE_USER=app",
                 "DATABASE_PASSWORD=$POSTGRESQL_PASSWORD"):
        assert line in script
    f = files_of(project("kubernetes", *K3S_HELM, "postgresql", postgresql={"url_format": "parts", "url_var": "DB_URL"}))
    values = minihelm.merge(yaml.safe_load(f["charts/shop/values.yaml"]),
                            yaml.safe_load(f["charts/shop/values-staging.yaml"]))
    values = minihelm.set_path(values, "database.postgresql.password", "pw")
    docs = minihelm.render_chart(f, "charts/shop", values, release="shop")
    env = {e["name"]: e for e in next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]
           ["containers"][0]["env"]}
    assert env["DB_HOST"]["value"] == "shop-postgresql" and env["DB_PORT"]["value"] == "5432"
    assert env["DB_PASSWORD"]["valueFrom"]["secretKeyRef"] == {"name": "shop-postgresql", "key": "password"}


def test_cloudnativepg_lit_les_cles_de_l_operateur():
    f = files_of(project("kubernetes", *K3S_KUST, "cloudnative-pg", cloudnative_pg={"url_format": "jdbc"}))
    dep = yaml.safe_load(f["deploy/kustomize/base/deployment.yaml"])
    env = dep["spec"]["template"]["spec"]["containers"][0]["env"]
    assert env[0]["valueFrom"]["secretKeyRef"] == {"name": "shop-pg-app", "key": "jdbc-uri"}
    f = files_of(project("kubernetes", *K3S_KUST, "cloudnative-pg", cloudnative_pg={"url_format": "parts"}))
    env = yaml.safe_load(f["deploy/kustomize/base/deployment.yaml"])["spec"]["template"]["spec"]["containers"][0]["env"]
    keys = {e["name"]: e["valueFrom"]["secretKeyRef"]["key"] for e in env}
    assert keys == {"DATABASE_URL": "uri", "DATABASE_HOST": "host", "DATABASE_PORT": "port", "DATABASE_NAME": "dbname",
                    "DATABASE_USER": "user", "DATABASE_PASSWORD": "password"}


def test_regles_de_connexion():
    managed = project("kubernetes-managed", "gitlab", "gitlab-ci", "aws", "eks", "helm", "aws-rds",
                      aws_rds={"url_format": "parts"})
    assert "R46" in rule_ids(managed)
    twice = project("docker-host", *COMPOSE, "postgresql", "mongodb", mongodb={"url_var": "DATABASE_URL"})
    assert "R46" in rule_ids(twice)
    assert "R46" not in rule_ids(project("docker-host", *COMPOSE, "postgresql", "mongodb"))


def test_analyse_reprend_la_variable_lue_par_l_application(tmp_path):
    spring = tmp_path / "spring"
    (spring / "src/main/resources").mkdir(parents=True)
    (spring / "pom.xml").write_text("<project><dependency><artifactId>spring-boot-starter-web</artifactId></dependency>"
                                    "<dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId>"
                                    "</dependency></project>")
    (spring / "src/main/resources/application.properties").write_text("spring.datasource.url=${JDBC_DATABASE_URL}\n")
    profile = appscan.scan(spring)
    assert profile.connections["sql"] == {"url_var": "JDBC_DATABASE_URL", "url_format": "jdbc"}
    a, _ = answers_from_profile(profile, CATALOG)
    a.hosting = "docker-host"
    p = build_starter(a, CATALOG)
    assert p.bricks_for("postgresql")[0].params == {"url_var": "JDBC_DATABASE_URL", "url_format": "jdbc"}
    django = tmp_path / "dj"
    django.mkdir()
    (django / "requirements.txt").write_text("django\npsycopg\n")
    (django / "settings.py").write_text('import os\nHOST = os.environ["DB_HOST"]\nPW = os.getenv("DB_PASSWORD")\n')
    assert appscan.scan(django).connections["sql"] == {"url_var": "DB_URL", "url_format": "parts"}
    node = tmp_path / "node"
    node.mkdir()
    (node / "package.json").write_text('{"dependencies": {"pg": "8", "ioredis": "5"}}')
    (node / "app.js").write_text("const a = process.env.PG_CONNECTION_URL; const b = process.env['CACHE_REDIS_URL'];")
    found = appscan.scan(node).connections
    assert found == {"sql": {"url_var": "PG_CONNECTION_URL"}, "key-value": {"url_var": "CACHE_REDIS_URL"}}


# ------------------------------------------------------------------ poste de développement
def test_bases_du_poste_meme_version_ports_locaux():
    f = files_of(project("kubernetes-managed", "gitlab", "gitlab-ci", "aws", "eks", "helm", "aws-rds", "mariadb",
                         "valkey", aws_rds={"engine": "mysql", "version": "8.4"}))
    dev = yaml.safe_load(f["dev/db/compose.yaml"])
    assert dev["services"]["mysql"]["image"] == "mysql:8.4" and dev["services"]["mariadb"]["image"] == "mariadb:11.8"
    assert dev["services"]["mysql"]["ports"] == ["127.0.0.1:3306:3306"]
    assert dev["services"]["mariadb"]["ports"] == ["127.0.0.1:3307:3306"]  # même port : décalé
    assert dev["services"]["adminer"]["profiles"] == ["outils"]
    env = f["dev/db/app.env"]
    assert "MARIADB_URL='mysql://app:dev@127.0.0.1:3307/app'" in env
    assert "REDIS_URL='redis://:dev@127.0.0.1:6379/0'" in env
    assert "dev/db/init/mysql/README.md" in f
    assert "Poste de développement" in f["docs/mise-en-route.md"]


@pytest.mark.skipif(not shutil.which("docker"), reason="docker absent")
def test_compose_du_poste_valide():
    with tempfile.TemporaryDirectory() as tmp:
        generate(project("docker-host", *COMPOSE, "postgresql"), CATALOG, ENGINE).write(tmp)
        r = subprocess.run(["docker", "compose", "-f", f"{tmp}/dev/db/compose.yaml", "config", "-q"])
        assert r.returncode == 0


# ------------------------------------------------------------------ restauration
SHIM = """#!/bin/sh
# docker compose … exec -T <service> sh -c <commande> : la commande contre la base locale
while [ $# -gt 0 ] && [ "$1" != "exec" ]; do shift; done
shift; [ "$1" = "-T" ] && shift; shift; shift; shift
exec sh -c "$1"
"""


def _pg_bin() -> Path | None:
    for base in sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True):
        if (base / "initdb").exists():
            return base
    return Path(shutil.which("initdb")).parent if shutil.which("initdb") else None


@pytest.fixture
def local_pg(tmp_path):
    """PostgreSQL éphémère (initdb) ; ignoré si le poste n'en a pas ou tourne en root sans compte postgres."""
    pg = _pg_bin()
    if pg is None or not shutil.which("pg_dump"):
        pytest.skip("PostgreSQL absent")
    run_as: list[str] = []
    if os.geteuid() == 0:
        if subprocess.run(["id", "postgres"], capture_output=True).returncode:
            pytest.skip("root sans compte postgres")
        run_as = ["su", "postgres", "-s", "/bin/sh", "-c"]
    data = Path(tempfile.mkdtemp(prefix="dbux-pg-"))  # hors de tmp_path : son parent n'est lisible que par root
    os.chmod(data, 0o755)
    if run_as:
        shutil.chown(data, "postgres")

    def sh(cmd: str):
        return subprocess.run([*run_as, cmd] if run_as else ["sh", "-c", cmd], capture_output=True, text=True)
    r = sh(f"{pg}/initdb -D {data}/d -U app --auth=trust")
    assert r.returncode == 0, r.stderr
    r = sh(f"{pg}/pg_ctl -D {data}/d -o '-p 55433 -k {data}' -l {data}/log -w start")
    assert r.returncode == 0, r.stderr
    env = {**os.environ, "PGHOST": str(data), "PGPORT": "55433", "PGUSER": "app",
           "POSTGRES_USER": "app", "POSTGRES_DB": "app"}
    subprocess.run(["psql", "-d", "postgres", "-qc", "create database app"], env=env, check=True)
    yield env
    sh(f"{pg}/pg_ctl -D {data}/d -m immediate stop")
    shutil.rmtree(data, ignore_errors=True)


def test_sauvegarde_puis_restauration_reelle(tmp_path, local_pg):
    repo = tmp_path / "repo"
    generate(project("docker-host", *COMPOSE, "postgresql"), CATALOG, ENGINE).write(repo)
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "docker").write_text(SHIM)
    (shim / "docker").chmod(0o755)
    env = {**local_pg, "PATH": f"{shim}:{os.environ['PATH']}"}
    psql = ["psql", "-d", "app", "-qtA", "-c"]
    subprocess.run([*psql, "create table t (id int, v text); insert into t values (1, 'avant')"], env=env, check=True)
    backups = tmp_path / "bk"
    subprocess.run(["sh", "scripts/db-backup.sh", "/opt/shop", str(backups)], cwd=repo, env=env, check=True,
                   capture_output=True)
    dump = next(backups.glob("postgresql-*.dump"))
    subprocess.run([*psql, "update t set v = 'abîmé'; insert into t values (2, 'en trop')"], env=env, check=True)
    refused = subprocess.run(["sh", "scripts/db-restore.sh", "/opt/shop", str(dump)], cwd=repo, env=env,
                             capture_output=True, text=True)
    assert refused.returncode == 1 and "relancer avec --oui" in refused.stderr
    subprocess.run(["sh", "scripts/db-restore.sh", "/opt/shop", str(dump), "--oui"], cwd=repo, env=env, check=True,
                   capture_output=True)
    out = subprocess.run([*psql, "select id, v from t order by id"], env=env, capture_output=True, text=True).stdout
    assert out.strip() == "1|avant"


def test_restauration_copiee_sur_les_hotes():
    ci = files_of(project("docker-host", *COMPOSE, "postgresql"))[".gitlab-ci.yml"]
    assert 'scp scripts/db-restore.sh "$DEPLOY_HOST_PRODUCTION:/opt/shop/db-restore.sh"' in ci
    site = files_of(project("vm", "gitlab", "gitlab-ci", "docker-compose", "ansible", "mariadb"))["ansible/deploy.yml"]
    assert "db-restore.sh" in site


# ------------------------------------------------------------------ sauvegardes CloudNativePG
def test_cloudnativepg_sauvegarde_vers_un_stockage_s3():
    p = project("kubernetes", *K3S_HELM, "cloudnative-pg", "cert-manager",
                cloudnative_pg={"backup_destination": "s3://shop-bk", "backup_endpoint": "https://s3.fr-par.scw.cloud"})
    f = files_of(p)
    values = yaml.safe_load(f["charts/shop/values.yaml"])
    docs = minihelm.render_chart(f, "charts/shop", values, release="shop", namespace="shop-staging")
    cluster = next(d for d in docs if d["kind"] == "Cluster")
    assert cluster["spec"]["plugins"] == [{"name": "barman-cloud.cloudnative-pg.io", "isWALArchiver": True,
                                           "parameters": {"barmanObjectName": "shop-backups"}}]
    store = next(d for d in docs if d["kind"] == "ObjectStore")
    conf = store["spec"]["configuration"]
    assert conf["destinationPath"] == "s3://shop-bk/shop-staging" and conf["endpointURL"] == "https://s3.fr-par.scw.cloud"
    assert conf["s3Credentials"]["accessKeyId"] == {"name": "shop-backup-credentials", "key": "ACCESS_KEY_ID"}
    sched = next(d for d in docs if d["kind"] == "ScheduledBackup")
    assert sched["spec"]["method"] == "plugin" and sched["spec"]["cluster"] == {"name": "shop-pg"}
    assert "helm upgrade --install plugin-barman-cloud cnpg/plugin-barman-cloud" in f["platform/install.sh"]
    assert "kubectl -n shop-staging create secret generic shop-backup-credentials" in f["docs/mise-en-route.md"]
    ids = rule_ids(p)
    assert "R40" not in ids and "R47" not in ids
    p.remove(p.bricks_for("cert-manager")[0].uid)
    assert "R47" in rule_ids(p)


def test_cloudnativepg_eks_bucket_et_pod_identity():
    f = files_of(project("kubernetes-managed", "gitlab", "gitlab-ci", "aws", "eks", "opentofu", "s3", "kustomize",
                         "cloudnative-pg", "cert-manager"))
    main = f["infra/terraform/main.tf"]
    assert 'bucket = "shop-db-backups"' in main
    assert 'resource "aws_eks_pod_identity_association" "db_backups_shop_staging"' in main
    assert 'service_account = "shop-pg"' in main and 'addon_name   = "eks-pod-identity-agent"' in main
    store = yaml.safe_load(f["deploy/kustomize/overlays/staging/objectstore.yaml"])
    assert store["spec"]["configuration"]["s3Credentials"] == {"inheritFromIAMRole": True}
    assert store["spec"]["configuration"]["destinationPath"] == "s3://shop-db-backups/shop-staging"


def test_cloudnativepg_gke_bucket_et_workload_identity(tmp_path):
    p = project("kubernetes-managed", "github", "github-actions", "gcp", "gke", "terraform", "gcs", "kustomize",
                "cloudnative-pg", "cert-manager")
    r = generate(p, CATALOG, ENGINE, allow_blocking=True)
    main = r.files["infra/terraform/main.tf"]
    assert 'resource "google_storage_bucket" "db_backups"' in main
    assert "subject/ns/shop/sa/shop-pg" in main
    if shutil.which("kustomize") or shutil.which("kubectl"):
        r.write(tmp_path)
        docs = kustomize_build(tmp_path, "deploy/kustomize/overlays/production")
        store = next(d for d in docs if d["kind"] == "ObjectStore")
        assert store["metadata"]["namespace"] == "shop"
        assert store["spec"]["configuration"]["googleCredentials"] == {"gkeEnvironment": True}


def test_sans_destination_rien_n_est_genere():
    f = files_of(project("kubernetes", *K3S_HELM, "cloudnative-pg"))
    assert "ObjectStore" not in f["charts/shop/templates/cloudnative-pg.yaml"]
    assert "plugin-barman-cloud" not in f["platform/install.sh"]
    assert "Destination des sauvegardes" in f["PIPELINE.md"]


def test_assistant_prend_la_connexion_detectee():
    a = StarterAnswers(hosting="kubernetes", database="postgresql",
                       connections={"sql": {"url_var": "SPRING_DATASOURCE_URL", "url_format": "jdbc"}})
    p = build_starter(a, CATALOG)
    assert p.bricks_for("cloudnative-pg")[0].params["url_format"] == "jdbc"
