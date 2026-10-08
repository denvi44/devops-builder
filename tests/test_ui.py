"""Tests de l'interface en mode hors écran (QT_QPA_PLATFORM=offscreen)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from devops_builder.catalog import DATA_DIR  # noqa: E402
from devops_builder.model import Project  # noqa: E402


@pytest.fixture(scope="module")
def win(tmp_path_factory):
    os.environ["HOME"] = str(tmp_path_factory.mktemp("home"))
    from devops_builder.ui.app import create_window
    app, window = create_window(["devops-builder"])
    window.show()
    app.processEvents()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_ajout_depuis_la_palette_et_annulation(win):
    win._load(Project(name="t"), None)
    win.add_tool(None, "gitlab", -1)
    win.add_tool(None, "gitlab-ci", -1)
    assert win.project.tool_ids() == {"gitlab", "gitlab-ci"}
    assert win.canvas.columns["source"].list.count() == 1
    win.undo_stack.undo()
    assert win.project.tool_ids() == {"gitlab"}
    win.undo_stack.redo()
    assert "gitlab-ci" in win.project.tool_ids()


def test_glisser_vers_une_autre_etape(win):
    win._load(Project(name="t"), None)
    win.canvas.toolDropped.emit("platform", "traefik", 0)
    uid = win.project.stages["platform"][0].uid
    win.canvas.brickMoved.emit(uid, "deploy", 0)
    assert win.project.stages["deploy"][0].tool == "traefik"
    assert win.project.stages["platform"] == []


def test_doublon_refuse(win):
    win._load(Project(name="t"), None)
    win.add_tool(None, "harbor", -1)
    win.add_tool(None, "harbor", -1)
    assert len(win.project.bricks_for("harbor")) == 1


def test_diagnostic_et_correction(win):
    p = Project(name="t", target="docker-host")
    p.add("argo-cd", "deploy")
    win._load(p, None)
    assert win.diagnostics.tree.topLevelItemCount() >= 1
    diag = win.engine.evaluate(win.project)[0]
    add_k3s = next(a for a in diag.actions if a.op == "add_brick")
    win.apply_fix(add_k3s)
    assert "k3s" in win.project.tool_ids()
    assert not [d for d in win.engine.evaluate(win.project) if d.rule_id == "R01"]
    win.undo_stack.undo()
    assert "k3s" not in win.project.tool_ids()


def test_parametres_de_brique(win):
    win._load(Project(name="t"), None)
    win.add_tool(None, "eks", -1)
    uid = win.project.bricks_for("eks")[0].uid
    win.set_params(uid, {"cluster_name": "prod"})
    assert win.project.find(uid)[2].params == {"cluster_name": "prod"}


def test_suppression_au_clavier(win):
    win._load(Project(name="t"), None)
    win.add_tool(None, "trivy", -1)
    uid = win.project.bricks_for("trivy")[0].uid
    win.canvas.deleteRequested.emit(uid)
    assert "trivy" not in win.project.tool_ids()


def test_exemples_et_generation(win, tmp_path):
    from devops_builder.generators import generate
    from devops_builder.ui.dialogs import GenerateDialog
    for path in sorted((DATA_DIR / "examples").glob("*.yaml")):
        win.undo_stack.setClean()  # sinon une boîte « Enregistrer ? » modale bloquerait le test
        win.open_path(path, as_template=True)
        win.undo_stack.setClean()
        result = generate(win.project, win.catalog, win.engine)
        dlg = GenerateDialog(result, win)
        assert dlg.tree.topLevelItemCount() > 0
        dlg.close()


def test_theme_sombre_puis_clair(win):
    win.toggle_theme()
    assert win.dark
    win.toggle_theme()
    assert not win.dark


def test_palette_filtres(win):
    pal = win.palette
    pal.search.setText("kyverno")
    assert pal.tree.topLevelItemCount() == 1
    pal.search.clear()
    pal.landscape.setChecked(True)
    assert "fiches vérifiées" in pal.count.text()
    pal.landscape.setChecked(False)
