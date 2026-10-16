# SPDX-License-Identifier: Apache-2.0
"""Accessibilité de l'interface : audit automatisé (EN 301 549, WCAG 2.1, RGAA) et corrections de la 0.20."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from devops_builder.catalog import DATA_DIR  # noqa: E402

EXAMPLE = DATA_DIR / "examples" / "01-web-hote-docker.devops.yaml"


@pytest.fixture(scope="module")
def win(tmp_path_factory):
    os.environ["HOME"] = str(tmp_path_factory.mktemp("home-a11y"))
    from devops_builder.ui.app import create_window
    app, window = create_window(["devops-builder"])
    window.show()
    window.activateWindow()
    window.open_path(EXAMPLE)
    app.processEvents()
    yield window
    window.undo_stack.setClean()
    window.close()


def test_audit_sans_constat_dans_les_deux_themes(win):
    from devops_builder.ui.audit import clipped_at, full_audit
    findings = []
    for _ in range(2):
        findings += full_audit(win) + clipped_at(win, 2.0)
        win.toggle_theme()
    assert not findings, "\n".join(map(str, findings))


def test_couleurs_des_deux_themes():
    from devops_builder.ui.audit import check_palettes, ratio
    from devops_builder.ui.theme import LIGHT
    assert not check_palettes()
    assert ratio(LIGHT.warning, LIGHT.background) >= 4.5  # #e65100 n'atteignait que 3,5:1


def test_textes_de_qt_en_francais(win):
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(QMessageBox.Icon.Question, "t", "t",
                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                      | QMessageBox.StandardButton.Cancel, win)
    texts = {box.button(b).text().replace("&", "") for b in (QMessageBox.StandardButton.Save,
                                                             QMessageBox.StandardButton.Cancel)}
    assert texts == {"Enregistrer", "Annuler"}


def test_messages_annonces_au_lecteur_d_ecran(win, monkeypatch):
    from devops_builder.ui import main_window
    said = []
    monkeypatch.setattr(main_window, "announce", lambda source, text, assertive=False: said.append(text))
    win.add_tool(None, "cosign", -1)
    assert any(t.startswith("Cosign ajouté à l'étape Sécurité") for t in said), said


def test_alt_haut_et_bas_deplacent_dans_l_etape(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    names = lambda: [b.tool for b in win.project.stages["build"]]  # noqa: E731
    first = names()
    lst = win.canvas.columns["build"].list
    lst.setFocus()
    lst.setCurrentRow(0)
    QTest.keyClick(lst, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    assert names()[1] == first[0] and names()[0] == first[1]
    lst = win.canvas.columns["build"].list
    QTest.keyClick(lst, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
    assert names() == first


def test_taille_du_texte(win):
    from devops_builder.ui import theme
    win.set_text_scale(1.5)
    assert theme.scale() == 1.5 and win.settings.value("text_scale", type=float) == 1.5
    assert win.title_row.indexOf(win.title) >= 0  # titre sur sa propre ligne
    assert win.canvas.columns["build"].width() == round(236 * 1.5)
    win._step_text(1)
    assert theme.scale() == 2.0
    win.set_text_scale(1.0)
    assert win.bar.indexOf(win.title) == 0 and theme.scale() == 1.0


def test_icones_decoratives_hors_de_l_arbre(win):
    from PySide6.QtWidgets import QLabel
    for col in win.canvas.columns.values():
        assert not [lbl for lbl in col.findChildren(QLabel) if lbl.pixmap() and not lbl.pixmap().isNull()]


def test_anneau_de_focus_suit_le_controle(win):
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QApplication

    from devops_builder.ui import a11y
    ring = a11y._ring
    target = win.palette.search
    win.activateWindow()
    target.setFocus()
    QApplication.processEvents()
    assert target.hasFocus()
    assert ring is not None and ring.isVisible() and ring.parentWidget() is win
    rect = QRect(target.mapTo(win, QPoint(0, 0)), target.size())
    assert ring.geometry().contains(rect)


def test_ligne_de_commande_ouvre_un_projet_dans_l_interface(monkeypatch):
    from devops_builder import cli
    from devops_builder.ui import app
    seen = []
    monkeypatch.setattr(app, "run", lambda argv=None: seen.append(argv) or 0)
    assert cli.main([str(EXAMPLE)]) == 0
    assert seen == [["devops-builder", str(EXAMPLE)]]
