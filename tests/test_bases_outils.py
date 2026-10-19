# SPDX-License-Identifier: Apache-2.0
"""0.22 : un PostgreSQL dédié à Gitea, SonarQube ou Grafana (paramètre « Base de données »)."""

from __future__ import annotations

import pytest
import yaml

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.model import Project, env_preset
from devops_builder.params import check_value

CATALOG = default_catalog()
TOOLS = ("gitea", "sonarqube", "grafana")


def project(target: str, *extra: str, dedicated: bool = True) -> Project:
    p = Project(name="t", target=target, environments=env_preset("staging-prod"))
    base = ("gitlab", "gitlab-ci", "buildkit", "docker-compose") if target == "docker-host" else (
        "gitlab", "gitlab-ci", "buildkit", "helm", "k3s")
    for t in (*base, *extra):
        p.add(t, CATALOG[t].stage)
    for t in TOOLS:
        p.add(t, CATALOG[t].stage, **({"database": "postgresql"} if dedicated else {}))
    return p


def compose(p: Project) -> dict:
    return yaml.safe_load(generate(p, CATALOG).files["deploy/docker-compose.yml"])["services"]


def test_base_integree_par_defaut():
    s = compose(project("docker-host", dedicated=False))
    assert not any(k.endswith("-db") for k in s)
    assert "GITEA__database__DB_TYPE" not in s["gitea"].get("environment", {})


@pytest.mark.parametrize("tool", TOOLS)
def test_service_de_base_compose(tool):
    s = compose(project("docker-host"))
    db = s[f"{tool}-db"]
    assert db["image"].startswith("postgres:")
    assert db["env_file"] == [f"secrets/{tool}-db.env"]
    assert db["volumes"] == [f"{tool}-db-data:/var/lib/postgresql/data"]
    assert "ports" not in db   # jamais publiée sur l'hôte
    assert s[tool]["depends_on"][f"{tool}-db"] == {"condition": "service_healthy"}


def test_variables_de_connexion_compose():
    s = compose(project("docker-host"))
    assert s["gitea"]["environment"]["GITEA__database__DB_TYPE"] == "postgres"
    assert s["sonarqube"]["environment"]["SONAR_JDBC_URL"] == "jdbc:postgresql://sonarqube-db:5432/sonarqube"
    assert s["grafana"]["environment"]["GF_DATABASE_HOST"] == "grafana-db:5432"


def test_mot_de_passe_jamais_ecrit_en_clair():
    f = generate(project("docker-host"), CATALOG).files
    script = f["deploy/secrets.sh"]
    assert "GITEA_DB_PASSWORD" in script and "POSTGRES_PASSWORD=$GITEA_DB_PASSWORD" in script
    assert "GITEA__database__PASSWD=$GITEA_DB_PASSWORD" in script
    assert "PASSWD=" not in f["deploy/docker-compose.yml"]


def test_une_base_par_instance():
    p = project("docker-host")
    p.add("gitea", CATALOG["gitea"].stage, instance="equipe-b", database="postgresql")
    s = compose(p)
    assert s["gitea-equipe-b"]["environment"]["GITEA__database__HOST"] == "gitea-equipe-b-db:5432"
    assert s["gitea-equipe-b-db"]["volumes"] != s["gitea-db"]["volumes"]
    script = generate(p, CATALOG).files["deploy/secrets.sh"]
    assert "GITEA_EQUIPE_B_DB_PASSWORD" in script


def test_cluster_cnpg_sur_kubernetes():
    f = generate(project("kubernetes", "cloudnative-pg"), CATALOG).files
    cluster = yaml.safe_load(f["platform/db-gitea.yaml"])
    assert cluster["kind"] == "Cluster" and cluster["metadata"]["namespace"] == "gitea"
    assert cluster["spec"]["bootstrap"]["initdb"] == {"database": "gitea", "owner": "gitea"}
    line = next(ln for ln in f["platform/install.sh"].splitlines() if ln.startswith("helm upgrade --install gitea "))
    assert "gitea.config.database.HOST=gitea-pg-rw:5432" in line
    assert "secretKeyRef.name=gitea-pg-app" in line
    assert "postgresql-ha.enabled=false" in line


def test_statefulset_sans_operateur():
    f = generate(project("kubernetes"), CATALOG).files
    kinds = [d["kind"] for d in yaml.safe_load_all(f["platform/db-sonarqube.yaml"]) if d]
    assert kinds == ["Service", "StatefulSet"]
    script = f["platform/install.sh"]
    assert "create secret generic sonarqube-db" in script
    assert "jdbcOverwrite.jdbcSecretName=sonarqube-db" in script


def test_grafana_helm_garde_le_point_echappe():
    line = next(ln for ln in generate(project("kubernetes"), CATALOG).files["platform/install.sh"].splitlines()
                if ln.startswith("helm upgrade --install grafana "))
    assert "'grafana\\.ini.database.type=postgres'" in line


def test_la_creation_precede_l_installation():
    lines = generate(project("kubernetes", "cloudnative-pg"), CATALOG).files["platform/install.sh"].splitlines()
    apply = next(i for i, ln in enumerate(lines) if "db-gitea.yaml" in ln)
    helm = next(i for i, ln in enumerate(lines) if ln.startswith("helm upgrade --install gitea "))
    assert apply < helm


def test_valeur_invalide_refusee():
    spec = CATALOG["gitea"].param_schema["database"]
    assert check_value(spec, "oracle") and check_value(spec, "postgresql") is None
