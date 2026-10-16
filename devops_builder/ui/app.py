# SPDX-License-Identifier: Apache-2.0
"""Lancement de l'interface graphique."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ..catalog import default_catalog
from ..messages import reason
from ..model import Project, ProjectFormatError
from ..rules import RuleEngine
from . import a11y, theme
from .main_window import MainWindow


def create_window(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    argv = argv if argv is not None else sys.argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("DevOps Builder")
    app.setOrganizationName("DevOpsBuilder")
    app.setFont(theme.default_font())
    a11y.install_translations(app)  # boutons standard, menus contextuels, sélecteur de fichiers en français
    a11y.install_focus_ring(app)
    catalog = default_catalog()
    engine = RuleEngine(catalog)

    project, path, problem = None, None, ""
    files = [a for a in argv[1:] if a.endswith((".yaml", ".yml"))]
    if files and Path(files[0]).exists():
        try:
            project, path = Project.load(files[0]), Path(files[0])
        except (ProjectFormatError, OSError) as exc:  # fenêtre vide et message, plutôt qu'un arrêt
            problem = f"{Path(files[0]).name} n'a pas pu être ouvert : " + (
                str(exc) if isinstance(exc, ProjectFormatError) else reason(exc))

    from PySide6.QtCore import QSettings
    dark = QSettings("DevOpsBuilder", "DevOpsBuilder").value("dark", False, type=bool)
    text_scale = QSettings("DevOpsBuilder", "DevOpsBuilder").value("text_scale", 1.0, type=float)
    theme.apply(app, dark, text_scale)  # type: ignore[arg-type]
    window = MainWindow(catalog, engine, project, path)
    if problem:
        window.statusBar().showMessage(problem, 15000)
    elif project is not None:
        window.announce_unknown_fields(project)
    return app, window  # type: ignore[return-value]


def run(argv: list[str] | None = None) -> int:
    app, window = create_window(argv)
    window.show()
    return app.exec()
