# SPDX-License-Identifier: Apache-2.0
"""0.21 : l'interface dit par où commencer (accueil d'un projet vide, prochaine étape, panneaux réduits)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from devops_builder.catalog import DATA_DIR  # noqa: E402

EXAMPLE = DATA_DIR / "examples" / "01-web-hote-docker.devops.yaml"


@pytest.fixture()
def win(tmp_path):
    home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    from devops_builder.ui.app import create_window
    app, window = create_window(["devops-builder"])
    window.show()
    app.processEvents()
    yield window
    window.undo_stack.setClean()
    window.close()
    if home is not None:
        os.environ["HOME"] = home


def test_projet_vide_montre_l_accueil_sans_panneaux(win):
    assert win.welcome.isVisible() and not win.canvas.isVisible() and not win.next_step.isVisible()
    assert not any(d.isVisible() for d in (win.palette_dock, win.props_dock, win.diag_dock))
    assert len(win.welcome.cards) == 5 and win.welcome.wizard.property("recommended")


def test_un_projet_remplace_l_accueil_et_rend_les_panneaux(win):
    win.open_path(EXAMPLE)
    assert not win.welcome.isVisible() and win.canvas.isVisible() and win.next_step.isVisible()
    assert all(d.isVisible() for d in (win.palette_dock, win.props_dock, win.diag_dock))
    win.new_empty_project()  # un projet vide ramène l'accueil
    assert win.welcome.isVisible() and not win.palette_dock.isVisible()


def test_modele_depuis_l_accueil(win):
    win.welcome.templateRequested.emit("scaleway")
    assert win.project.name == "Modèle Scaleway" and win.canvas.isVisible()


def test_construire_a_la_main_ouvre_le_catalogue(win):
    win.welcome.manualRequested.emit()
    assert not win.welcome.isVisible() and win.canvas.isVisible() and win.palette_dock.isVisible()
    assert win.palette.search.hasFocus() or win.palette.search.isVisible()


def test_prochaine_etape_suit_le_projet(win):
    from devops_builder.model import Severity
    from devops_builder.ui.accueil import next_step
    win.welcome.templateRequested.emit("aws")
    diags = win.engine.evaluate(win.project)
    assert next_step(win.project, diags, Severity.BLOCKING)[2:] == ("diagnostics", "warning")
    assert next_step(win.project, [], Severity.BLOCKING)[2] == "application"  # dossier de l'application non désigné
    win.project.app.source = "/tmp/app"
    assert next_step(win.project, [], Severity.BLOCKING)[2:] == ("generer", "ok")


def test_filtres_du_catalogue_replies(win):
    win.open_path(EXAMPLE)  # les panneaux n'apparaissent qu'une fois le projet commencé
    p = win.palette
    assert not p.filters_box.isVisible() and "Filtres" in p.filters_toggle.text()
    p.filters_toggle.setChecked(True)
    assert p.filters_box.isVisible() and p.oss.isVisible()
    p.oss.setChecked(True)
    assert "actif" in p.filters_toggle.text()


def test_barre_d_outils_allegee(win):
    names = [a.text() for a in win.toolbar.actions() if a.text()]
    assert "Générer les fichiers…" not in names and "Thème sombre" not in names
