# SPDX-License-Identifier: Apache-2.0
"""Robustesse : nom d'image, recherche du catalogue, outil inconnu, erreurs de la CLI."""
from __future__ import annotations

import pytest
import yaml

from devops_builder.catalog import default_catalog
from devops_builder.cli import main
from devops_builder.model import Project
from devops_builder.rules import RuleEngine, apply_action

CAT = default_catalog()
ENGINE = RuleEngine(CAT)


def _ids(p):
    return {d.rule_id for d in ENGINE.evaluate(p)}


@pytest.mark.parametrize("name", ["Mon App", "../x", "a b", "UP", "", "x" * 90, "-a"])
def test_nom_image_invalide_bloque_et_se_corrige(name):
    p = Project(name="t")
    p.app.image_name = name
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R57")
    assert diag.severity.value == "bloquant" or str(diag.severity).endswith("BLOCKING")
    apply_action(p, diag.actions[0], CAT)
    assert "R57" not in _ids(p)


@pytest.mark.parametrize("name", ["mon-app", "app.v2", "a_b-c", "x"])
def test_nom_image_valide(name):
    p = Project(name="t")
    p.app.image_name = name
    assert "R57" not in _ids(p)


def test_recherche_sans_accent_et_dans_le_desordre():
    assert CAT.search("repartiteur") == CAT.search("RÉPARTITEUR")
    assert {t.id for t in CAT.search("messages file")} & {"aws-sqs", "azure-service-bus"}
    assert "scaleway-lb" in {t.id for t in CAT.search("répartiteur de charge")}
    assert CAT.search("zzzzqq") == []


def test_recherche_classe_le_nom_avant_la_description():
    ids = [t.id for t in CAT.search("postgres")]
    assert ids.index("postgresql") < ids.index("sonarqube")


def test_outil_inconnu_diagnostique_et_retirable():
    p = Project(name="t")
    p.add("outil-disparu", "build")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R58")
    assert "outil-disparu" in diag.message
    apply_action(p, diag.actions[0], CAT)
    assert "R58" not in _ids(p)


def _write(tmp_path, project):
    f = tmp_path / "p.devops.yaml"
    f.write_text(yaml.safe_dump(project.model_dump(mode="json")), encoding="utf-8")
    return str(f)


def test_generate_sortie_impossible_sans_traceback(tmp_path, capsys):
    f = _write(tmp_path, Project(name="t"))
    (tmp_path / "fichier").write_text("x")
    code = main(["generate", f, "-o", str(tmp_path / "fichier" / "sous")])
    assert code == 2
    assert "Écriture impossible" in capsys.readouterr().err


def test_generate_force_sans_environnement(tmp_path):
    p = Project(name="t")
    p.environments = []
    f = _write(tmp_path, p)
    assert main(["generate", f, "-o", str(tmp_path / "o"), "--force"]) == 0
