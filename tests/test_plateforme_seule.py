# SPDX-License-Identifier: Apache-2.0
"""Projet « plateforme seule » : des outils sur un hôte Docker, sans application à construire ni à livrer."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import yaml
from test_data import CATALOG, ENGINE, project

from devops_builder.generators import generate
from devops_builder.model import Project
from devops_builder.ports import port_plan
from devops_builder.rules import apply_action

EXAMPLE = Path(__file__).parents[1] / "devops_builder" / "data" / "examples" / "05-labo-hote-docker.devops.yaml"


def labo(*tools: str, target: str = "docker-host", **params) -> Project:
    p = project(target, "docker-compose", *tools, envs="prod", **params)
    p.name = "Labo DevOps"
    p.app.enabled = False
    return p


def rules(p: Project) -> dict[str, str]:
    return {d.rule_id: d.message for d in ENGINE.evaluate(p)}


def test_ni_application_ni_pipeline():
    r = generate(labo("zabbix", "gitea", "jenkins", "grafana", zabbix={"supervise_host": False}), CATALOG, ENGINE,
                 allow_blocking=True)
    doc = yaml.safe_load(r.files["deploy/docker-compose.yml"])
    assert doc["name"] == "labo-devops" and "shop" not in doc["services"] and "migrate" not in doc["services"]
    assert {"gitea", "jenkins", "grafana", "zabbix-server"} <= set(doc["services"])   # forge et CI : des services
    assert not any(f.startswith((".gitlab-ci", ".github/", "Jenkinsfile", "scripts/ci-variables")) for f in r.files)
    assert "sans application" in r.files["PIPELINE.md"] and "Image publiée" not in r.files["PIPELINE.md"]
    assert all(e.component_id != "app" for e in port_plan(r.ir.project, CATALOG))


def test_sans_ci_ni_build_aucun_blocage():
    found = rules(labo("zabbix", "grafana", "prometheus"))
    assert not {"R27", "R28", "R59"} & set(found), found


def test_guide_commence_par_le_demarrage():
    text = generate(labo("zabbix", "grafana"), CATALOG, ENGINE).files["docs/mise-en-route.md"]
    titles = [line for line in text.splitlines() if line.startswith("## ")]
    assert titles[1].endswith("Démarrer la plateforme") and "pour démarrer la plateforme" in text
    assert "docker compose up -d\n" in text and "docker compose down" in text
    assert "http://$HOTE:3000" in text and "Hôtes" not in "".join(titles) and "SSH_PRIVATE_KEY" not in text
    assert 'sh scripts/db-backup.sh "$PWD/deploy" "$PWD/sauvegardes"' in text
    assert "export COMPOSE_PROJECT_NAME=labo-devops" in text and "   # " not in text


def test_briques_de_pipeline_signalees_et_retirables():
    p = labo("zabbix", "buildkit", "trivy")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R59")
    assert "BuildKit" in diag.message and "Trivy" in diag.message and "n'ont rien" in diag.message
    apply_action(p, diag.actions[0], CATALOG)
    assert "R59" not in rules(p) and not p.bricks_for("buildkit")


def test_hors_hote_docker_bloque_avec_retour_possible():
    p = labo(target="kubernetes")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R59")
    assert "hôte Docker" in diag.message
    apply_action(p, diag.actions[0], CATALOG)
    assert p.app.enabled and "R59" not in rules(p)


def test_adresse_de_l_application_sans_objet():
    assert "R34" not in rules(labo("traefik", "grafana", grafana={"hostname": "grafana.labo.fr"}))


def test_fichier_projet_stable_et_relu():
    with_app = project("docker-host", "docker-compose")
    assert "enabled" not in with_app.to_yaml()          # fichiers existants inchangés
    again = Project.from_yaml(labo("zabbix").to_yaml())
    assert again.app.enabled is False


def test_exemple_labo_sans_diagnostic():
    p = Project.load(EXAMPLE)
    assert not p.app.enabled and ENGINE.evaluate(p) == []
    assert "deploy/docker-compose.yml" in generate(p, CATALOG, ENGINE).files


def test_archive_dans_son_dossier_scripts_executables():
    r = generate(labo("zabbix"), CATALOG, ENGINE)
    with zipfile.ZipFile(io.BytesIO(r.zip_bytes())) as zf:
        names = zf.namelist()
        assert names and all(n.startswith("labo-devops/") for n in names)
        assert zf.getinfo("labo-devops/deploy/secrets.sh").external_attr >> 16 == 0o755
        assert zf.getinfo("labo-devops/PIPELINE.md").external_attr >> 16 == 0o644


def test_tutoriel_labo_fidele_a_la_generation():
    """Le tutoriel « Premier labo » ne cite que des fichiers générés pour l'exemple, et son dossier d'archive."""
    from test_guide import cited
    page = (Path(__file__).parents[1] / "docs" / "guide" / "tutoriels" / "labo.md").read_text(encoding="utf-8")
    r = generate(Project.load(EXAMPLE), CATALOG, ENGINE)
    names = {Path(f).name for f in r.files}
    missing = [ref for ref in sorted(cited(page)) if ref not in r.files and ref not in names]
    assert not missing, missing
    assert f"`{r.folder}`" in page and "Démarrer la plateforme" in r.files["docs/mise-en-route.md"]
