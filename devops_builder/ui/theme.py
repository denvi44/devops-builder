"""Thème Material (qt-material) avec des couleurs au contraste vérifié (WCAG AA).

Les thèmes « teal » fournis par qt-material utilisent #1de9b6, illisible en
texte sur fond blanc (contraste 1,5:1) ; on les remplace par des variantes
sombres de la même teinte.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

THEMES_DIR = Path(__file__).parent / "themes"


@dataclass(frozen=True)
class Palette:
    dark: bool
    primary: str
    primary_light: str
    surface: str        # fond des cartes
    background: str     # fond de fenêtre
    border: str
    text: str
    text_muted: str
    blocking: str = "#d32f2f"
    warning: str = "#e65100"
    info: str = "#1565c0"
    ok: str = "#2e7d32"

    def severity(self, value: str) -> str:
        return {"bloquant": self.blocking, "avertissement": self.warning, "info": self.info}.get(value, self.text_muted)


LIGHT = Palette(False, "#00796b", "#48a999", "#ffffff", "#f5f5f5", "#d6d6d6", "#212121", "#5f6368")
DARK = Palette(True, "#4db6ac", "#82e9de", "#2b3035", "#202326", "#3d444b", "#eceff1", "#b0bec5",
               blocking="#ef9a9a", warning="#ffb74d", info="#90caf9", ok="#a5d6a7")

_current: Palette = LIGHT


def current() -> Palette:
    return _current


def qcolor(hex_value: str, alpha: int | None = None) -> QColor:
    c = QColor(hex_value)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def _extra_qss(p: Palette) -> str:
    return f"""
QMainWindow, QDialog {{ background: {p.background}; }}
QFrame#stageCard {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
QLabel#stageTitle {{ font-weight: 600; font-size: 14px; color: {p.text}; }}
QLabel#stageCount {{ color: {p.text_muted}; }}
QLabel#sectionTitle {{ font-weight: 600; font-size: 13px; color: {p.text}; text-transform: none; }}
QLabel#heroTitle {{ font-size: 20px; font-weight: 600; color: {p.text}; }}
QLabel#muted {{ color: {p.text_muted}; }}
QLabel[chip="true"] {{
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 2px 8px;
    color: {p.text};
    background: {p.background};
}}
QLabel[chip="primary"] {{
    border: 1px solid {p.primary};
    border-radius: 10px;
    padding: 2px 8px;
    color: {p.primary};
}}
QFrame#projectBar {{
    background: {p.surface};
    border-bottom: 1px solid {p.border};
}}
QListWidget#stageList {{
    background: transparent;
    border: none;
}}
QListWidget#stageList::item, QListWidget#stageList::item:selected,
QListWidget#stageList::item:hover {{ background: transparent; border: none; }}
QScrollArea#canvasScroll, QWidget#canvasInner {{ background: {p.background}; border: none; }}
QPlainTextEdit#codePreview {{ font-family: "DejaVu Sans Mono", "Consolas", monospace; font-size: 12px; }}
QPushButton {{ text-transform: none; }}
QToolBar {{ spacing: 6px; }}
QToolBar QToolButton {{ text-transform: none; }}
QTabBar::tab {{ text-transform: none; }}
QDockWidget {{ text-transform: none; }}
QHeaderView::section {{ text-transform: none; }}
"""


def _theme_file(dark: bool) -> Path:
    return THEMES_DIR / ("devops_dark.xml" if dark else "devops_light.xml")


def apply(app: QApplication, dark: bool = False) -> Palette:
    """Applique le thème Material ; retourne la palette utilisée pour le dessin."""
    global _current
    import qt_material  # importé après PySide6, comme l'exige qt-material

    _current = DARK if dark else LIGHT
    extra = {"density_scale": "-1", "font_family": "Roboto, Inter, DejaVu Sans", "font_size": "13px"}
    qt_material.apply_stylesheet(app, theme=str(_theme_file(dark)), invert_secondary=not dark, extra=extra)
    app.setStyleSheet(app.styleSheet() + _extra_qss(_current))
    qpal = app.palette()
    for role in (QPalette.ColorRole.Link, QPalette.ColorRole.LinkVisited):
        qpal.setColor(role, QColor(_current.primary))
    app.setPalette(qpal)
    return _current


def default_font() -> QFont:
    families = set(QFontDatabase.families())
    for name in ("Roboto", "Inter", "DejaVu Sans"):
        if name in families:
            return QFont(name, 10)
    return QFont()
