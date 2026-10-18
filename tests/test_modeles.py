# SPDX-License-Identifier: Apache-2.0
"""Pipelines types par fournisseur cloud : sans blocage, fichiers valides, accessibles depuis l'interface et la CLI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.model import Project
from devops_builder.modeles import MODELES, build
from devops_builder.rules import RuleEngine

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
ROOT = Path(__file__).resolve().parent.parent
PROVIDER = {slug: m.answers.cloud for slug, m in MODELES.items()}


@pytest.mark.parametrize("slug", list(MODELES))
def test_modele_sans_blocage_et_valide(slug, tmp_path):
    from test_generators import _check_yaml, _validate_with_tools
    p = build(slug, CATALOG)
    assert p.description == MODELES[slug].description
    assert PROVIDER[slug] in p.tool_ids(), "le fournisseur du modèle est dans le pipeline"
    diags = ENGINE.evaluate(p)
    assert {d.rule_id for d in diags} <= {"R34"}, [(d.rule_id, d.message) for d in diags]  # valeurs à renseigner
    result = generate(p, CATALOG)
    assert "infra/terraform/main.tf" in result.files and "docs/mise-en-route.md" in result.files
    _check_yaml(result.files)
    result.write(tmp_path)
    _validate_with_tools(tmp_path, result.files)


def test_un_modele_par_fournisseur_du_catalogue():
    providers = {t.id for t in CATALOG.tools.values() if t.curated and t.kind == "provider"}
    assert set(PROVIDER.values()) == providers
    assert {"aws-ecs", "aws-ec2", "gcp-cloud-run", "azure-vm", "ovhcloud-vm", "scaleway-instance"} <= set(MODELES)


def test_ligne_de_commande(tmp_path, capsys):
    from devops_builder.cli import main
    assert main(["template"]) == 0
    listing = capsys.readouterr().out
    assert all(slug in listing for slug in MODELES)
    out = tmp_path / "p.devops.yaml"
    assert main(["template", "scaleway", "-o", str(out)]) == 0
    assert "kapsule" in Project.load(out).tool_ids()
    assert main(["template", "mars", "-o", str(out)]) == 2


def test_menu_de_l_interface(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        from devops_builder.ui.app import create_window
        app, win = create_window(["devops-builder"])
        menu = next(a.menu() for a in win.menuBar().actions() if a.text() == "&Fichier")
        sub = next(a.menu() for a in menu.actions() if a.text() == "Nouveau depuis un modèle de fournisseur")
        titles = [a.text() for a in sub.actions()]
        assert titles == [m.title for m in MODELES.values()]
        sub.actions()[0].trigger()
        assert win.project.name == "Modèle AWS" and win.path is None
        win.undo_stack.setClean()
        win.close()
    finally:
        if home is not None:
            os.environ["HOME"] = home


def test_guide_decrit_chaque_modele():
    page = (ROOT / "docs" / "guide" / "modeles.md").read_text(encoding="utf-8")
    for slug, m in MODELES.items():
        assert f"devops-builder template {slug}`" in page
        if "-" not in slug:  # les variantes sont décrites par leur commande, les modèles de base aussi par leur titre
            assert m.title in page
