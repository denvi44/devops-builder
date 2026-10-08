"""Tests de l'interface en mode hors écran (QT_QPA_PLATFORM=offscreen)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from devops_builder.catalog import DATA_DIR  # noqa: E402
from devops_builder.model import Project  # noqa: E402


@pytest.fixture(autouse=True)
def exceptions_dans_les_slots(monkeypatch):
    """Qt affiche les exceptions levées dans un slot sans faire échouer le test : on les capture."""
    import sys
    errors: list[BaseException] = []
    monkeypatch.setattr(sys, "excepthook", lambda typ, val, tb: errors.append(val))
    yield
    assert not errors, f"exception dans un slot Qt : {errors[0]!r}"


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


def _drop(win, stage: str, mime: str, payload: str) -> bool:
    """Envoie un vrai couple dragEnter / drop à la colonne ; retourne True si accepté."""
    from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import QApplication
    lst = win.canvas.columns[stage].list
    md = QMimeData()
    md.setData(mime, payload.encode())
    enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, md,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    lst.dragEnterEvent(enter)
    if not enter.isAccepted():
        return False
    drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, md,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    lst.dropEvent(drop)
    QApplication.processEvents()  # la modification est différée après le glisser
    return drop.isAccepted()


def test_depot_refuse_dans_une_etape_incompatible(win):
    from devops_builder.ui.palette import MIME_TOOL
    win._load(Project(name="t"), None)
    assert not _drop(win, "test", MIME_TOOL, "traefik")
    assert not _drop(win, "source", MIME_TOOL, "argo-cd")
    assert win.project.all_bricks() == []
    assert "ne peut pas aller" in win.statusBar().currentMessage()
    assert _drop(win, "platform", MIME_TOOL, "traefik")
    assert win.project.stages["platform"][0].tool == "traefik"


def test_etape_secondaire_acceptee(win):
    from devops_builder.ui.palette import MIME_TOOL
    win._load(Project(name="t"), None)
    assert _drop(win, "deploy", MIME_TOOL, "ansible")
    assert win.project.stages["deploy"][0].tool == "ansible"


def test_deplacement_de_brique_controle(win):
    from devops_builder.ui.canvas import MIME_BRICK
    win._load(Project(name="t"), None)
    win.add_tool(None, "ansible", -1)
    uid = win.project.bricks_for("ansible")[0].uid
    assert not _drop(win, "observability", MIME_BRICK, f"{uid}|ansible")
    assert win.project.stages["infrastructure"][0].uid == uid
    assert _drop(win, "deploy", MIME_BRICK, f"{uid}|ansible")
    assert win.project.stages["deploy"][0].uid == uid
    # Signal direct (ancien chemin) : refusé aussi
    win.canvas.brickMoved.emit(uid, "source", 0)
    assert win.project.stages["source"] == []


def test_mise_en_evidence_pendant_le_glisser(win):
    win.canvas.highlight("argo-cd")
    states = {sid: col.property("dropState") for sid, col in win.canvas.columns.items()}
    assert states["deploy"] == "ok"
    assert all(v == "no" for k, v in states.items() if k != "deploy")
    win.canvas.clear_highlight()
    assert all(col.property("dropState") == "" for col in win.canvas.columns.values())


def test_alt_fleches_saute_aux_etapes_autorisees(win):
    win._load(Project(name="t"), None)
    win.add_tool(None, "ansible", -1)
    uid = win.project.bricks_for("ansible")[0].uid
    win.shift_brick(uid, +1)
    assert win.project.find(uid)[0] == "deploy"
    win.shift_brick(uid, +1)  # aucune étape autorisée plus à droite
    assert win.project.find(uid)[0] == "deploy"
    win.add_tool(None, "argo-cd", -1)
    argo = win.project.bricks_for("argo-cd")[0].uid
    win.shift_brick(argo, -1)
    assert win.project.find(argo)[0] == "deploy"


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


def test_formulaire_de_parametres(win):
    from devops_builder.ui.param_form import ParamForm
    win._load(Project(name="t", target="kubernetes-managed"), None)
    win.add_tool(None, "aws", -1)
    win.add_tool(None, "eks", -1)
    uid = win.project.bricks_for("eks")[0].uid
    win._focus_brick(uid)
    form = win.properties.form
    assert isinstance(form, ParamForm)
    region = form.editors["region"]
    region.setCurrentText("Paris")
    assert form.errors["region"].isVisibleTo(form)          # erreur affichée pendant la saisie
    region.setCurrentText("eu-west-1")
    assert not form.errors["region"].isVisibleTo(form)
    form.editors["cluster_name"].setText("prod")
    form._commit()
    assert win.project.find(uid)[2].params == {"region": "eu-west-1", "cluster_name": "prod"}
    assert not [d for d in win.engine.evaluate(win.project) if d.rule_id in ("R32", "R34")]


def test_parametre_inconnu_supprime_depuis_le_formulaire(win):
    p = Project(name="t", target="kubernetes-managed")
    p.add("aws", "infrastructure")
    b = p.add("eks", "infrastructure")
    b.params = {"clustr_name": "x", "cluster_name": "prod"}
    win._load(p, None)
    win._focus_brick(b.uid)
    win.properties.form._drop_unknown("clustr_name")
    assert win.project.find(b.uid)[2].params == {"cluster_name": "prod"}


def test_formulaire_avec_valeurs_existantes_invalides(win):
    p = Project(name="t", target="kubernetes-managed")
    p.add("aws", "infrastructure")
    b = p.add("eks", "infrastructure")
    b.params = {"cluster_name": "prod", "region": "Paris"}
    win._load(p, None)
    win._focus_brick(b.uid)  # ne doit pas lever pendant la construction du formulaire
    form = win.properties.form
    assert form.editors["region"].currentText() == "Paris"
    assert form.errors["region"].isVisibleTo(form)
