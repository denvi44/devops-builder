"""Lancement de l'interface graphique."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ..catalog import default_catalog
from ..model import Project
from ..rules import RuleEngine
from . import theme
from .main_window import MainWindow


def create_window(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    argv = argv if argv is not None else sys.argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("DevOps Builder")
    app.setOrganizationName("DevOpsBuilder")
    app.setFont(theme.default_font())
    catalog = default_catalog()
    engine = RuleEngine(catalog)

    project, path = None, None
    files = [a for a in argv[1:] if a.endswith((".yaml", ".yml"))]
    if files and Path(files[0]).exists():
        path = Path(files[0])
        project = Project.load(path)

    from PySide6.QtCore import QSettings
    dark = QSettings("DevOpsBuilder", "DevOpsBuilder").value("dark", False, type=bool)
    theme.apply(app, dark)  # type: ignore[arg-type]
    window = MainWindow(catalog, engine, project, path)
    return app, window  # type: ignore[return-value]


def run() -> int:
    app, window = create_window()
    window.show()
    return app.exec()
