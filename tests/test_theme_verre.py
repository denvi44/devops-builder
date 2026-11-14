# SPDX-License-Identifier: Apache-2.0
"""Thème Verre : troisième thème, imitation dessinée par l'application, contrastes vérifiés au pire cas."""

from __future__ import annotations

import os

import pytest

from devops_builder.ui import theme
from devops_builder.ui.audit import blend, palette_pairs, ratio


@pytest.fixture
def qtbot_window(tmp_path):
    home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)   # réglages Qt jetables
    from devops_builder.ui.app import create_window
    app, window = create_window(["devops-builder"])
    window.show()
    app.processEvents()
    yield window
    window.set_theme("clair")
    window.undo_stack.setClean()
    window.close()
    if home is not None:
        os.environ["HOME"] = home


def test_trois_themes_declares():
    assert list(theme.THEMES) == ["clair", "sombre", "verre"]
    assert theme.GLASS.glass and not theme.GLASS.dark and not theme.LIGHT.glass
    assert theme.palette_of(True) is theme.DARK and theme.palette_of("inconnu") is theme.LIGHT


def test_fond_de_reference_est_l_arret_le_plus_sombre():
    from PySide6.QtGui import QColor

    from devops_builder.ui.audit import luminance
    darkest = min(theme.GLASS_STOPS, key=lambda c: luminance(QColor(c)))
    assert theme.GLASS.background == darkest


@pytest.mark.parametrize("stop", theme.GLASS_STOPS)
def test_contrastes_sur_chaque_arret_du_degrade(stop):
    """Texte posé directement sur le dégradé, et sur un panneau translucide (58 % de blanc) composé sur lui."""
    p = theme.GLASS
    panel = blend("#ffffff", stop, round(0.58 * 255)).name()
    for fg in (p.text, p.text_muted, p.primary, p.blocking, p.warning, p.info, p.ok):
        assert ratio(fg, stop) >= 4.5, (fg, stop)
        assert ratio(fg, panel) >= 4.5, (fg, panel)


def test_couples_dessines_a_la_main():
    for name, fg, bg, need in palette_pairs(theme.GLASS):
        assert ratio(fg, bg) >= need, name


def test_feuille_de_style_translucide_seulement_pour_le_verre():
    assert "qlineargradient" in theme._glass_qss(theme.GLASS)
    assert "qlineargradient" not in theme._extra_qss(theme.LIGHT)


def test_bascule_et_reglage_retenu(qtbot_window):
    win = qtbot_window
    win.set_theme("verre")
    assert win.theme_name == "verre" and win.a_glass.isChecked() and not win.a_theme.isChecked()
    assert win.settings.value("theme") == "verre" and theme.current() is theme.GLASS
    win.toggle_theme()                     # Ctrl+T depuis Verre : sombre
    assert win.dark and not win.a_glass.isChecked()
    win.toggle_glass()
    assert win.theme_name == "verre"
    win.toggle_glass()
    assert win.theme_name == "clair"
