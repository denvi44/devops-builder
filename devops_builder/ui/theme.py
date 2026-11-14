# SPDX-License-Identifier: Apache-2.0
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
    warning: str = "#bf360c"   # orange foncé : 5,1:1 sur le fond clair (#e65100 n'atteignait que 3,5:1)
    info: str = "#1565c0"
    ok: str = "#2e7d32"

    name: str = "clair"
    glass: bool = False        # panneaux translucides sur un fond en dégradé (thème Verre)

    def severity(self, value: str) -> str:
        return {"bloquant": self.blocking, "avertissement": self.warning, "info": self.info}.get(value, self.text_muted)


LIGHT = Palette(False, "#00695c", "#48a999", "#ffffff", "#f5f5f5", "#d6d6d6", "#212121", "#5f6368")
DARK = Palette(True, "#80cbc4", "#b2fef7", "#2b3035", "#202326", "#3d444b", "#eceff1", "#b0bec5",
               blocking="#ef9a9a", warning="#ffb74d", info="#90caf9", ok="#a5d6a7", name="sombre")
# Verre : imitation dessinée par l'application, identique sur tous les systèmes (pas l'effet natif de macOS 26).
# Fond en dégradé pastel, panneaux blancs translucides. « background » est l'arrêt le plus sombre du dégradé et
# « surface » le panneau composé sur lui : les contrastes se vérifient donc dans le cas le moins favorable.
GLASS_STOPS = ("#d3e4fb", "#eae3fc", "#d2efe5")
GLASS = Palette(False, "#00574b", "#3d8f81", "#eef4fc", "#d3e4fb", "#9fb1c7", "#14202c", "#3c4856",
                blocking="#b3261e", warning="#9a3a00", info="#0b4a9e", ok="#1b5e20", name="verre", glass=True)
THEMES: dict[str, Palette] = {p.name: p for p in (LIGHT, DARK, GLASS)}
THEME_LABELS = {"clair": "Clair", "sombre": "Sombre", "verre": "Verre"}

_current: Palette = LIGHT
# Taille du texte choisie dans Affichage (WCAG 1.4.4 : jusqu'à 200 % sans perte de contenu)
TEXT_SCALES = (1.0, 1.25, 1.5, 2.0)
_scale = 1.0


def scale() -> float:
    return _scale


def px(value: float) -> int:
    """Dimension proportionnelle à la taille du texte choisie."""
    return round(value * _scale)


def current() -> Palette:
    return _current


def qcolor(hex_value: str, alpha: int | None = None) -> QColor:
    c = QColor(hex_value)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def _rgba(hex_value: str, alpha: float) -> str:
    c = QColor(hex_value)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def _extra_qss(p: Palette) -> str:
    return f"""
QMainWindow, QDialog {{ background: {p.background}; }}
QFrame#stageCard {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
QFrame#stageCard[dropState="ok"] {{
    border: 2px solid {p.primary};
    background: {p.surface};
}}
QFrame#stageCard[dropState="no"] {{
    border: 1px dashed {p.border};
    background: {p.background};
}}
QLabel#stageTitle {{ font-weight: 600; font-size: {px(14)}px; color: {p.text}; }}
QFrame#stageCard[dropState="no"] QLabel#stageTitle {{ color: {p.text_muted}; }}
QLabel#stageCount {{ color: {p.text_muted}; }}
QLabel#sectionTitle {{ font-weight: 600; font-size: {px(13)}px; color: {p.text}; text-transform: none; }}
QLabel#heroTitle {{ font-size: {px(20)}px; font-weight: 600; color: {p.text}; }}
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
QFrame#welcome, QScrollArea#welcomeScroll, QWidget#welcomeContent {{ background: {p.background}; border: none; }}
QPushButton#startCard {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 12px;
    text-align: left;
    text-transform: none;
}}
QPushButton#startCard[recommended="true"] {{ border: 2px solid {p.primary}; }}
QPushButton#startCard:hover {{ border-color: {p.primary}; background: {_rgba(p.primary, 0.06)}; }}
QPushButton#startCard::menu-indicator {{ subcontrol-origin: padding; subcontrol-position: right center; right: 14px; }}
QLabel#startTitle {{ font-size: {px(15)}px; font-weight: 600; color: {p.text}; background: transparent; }}
QPushButton#startCard QLabel#muted {{ background: transparent; }}
QFrame#nextStep {{ background: {_rgba(p.primary, 0.08)}; border-bottom: 1px solid {p.border}; }}
QFrame#nextStep[tone="blocking"] {{ background: {_rgba(p.blocking, 0.10)}; }}
QFrame#nextStep[tone="warning"] {{ background: {_rgba(p.warning, 0.10)}; }}
QLabel#nextStepText {{ color: {p.text}; background: transparent; }}
QToolButton#filtersToggle {{ border: none; text-align: left; padding: 4px 2px; text-transform: none; }}
QListWidget#stageList {{
    background: transparent;
    border: none;
}}
QListWidget#stageList::item, QListWidget#stageList::item:selected,
QListWidget#stageList::item:hover {{ background: transparent; border: none; }}
QScrollArea#canvasScroll, QWidget#canvasInner {{ background: {p.background}; border: none; }}
QPlainTextEdit#codePreview {{ font-family: "DejaVu Sans Mono", "Consolas", monospace; font-size: {px(12)}px; }}
QPushButton {{ text-transform: none; }}
QToolButton:focus, QPushButton:focus, QPushButton:flat:focus {{ background-color: {_rgba(p.primary, 0.12)}; }}
QPushButton#viewsButton {{ padding-right: 22px; }}
QPushButton#viewsButton::menu-indicator {{ subcontrol-origin: padding; subcontrol-position: right center; right: 6px; }}
QToolBar {{ spacing: 6px; }}
QToolBar QToolButton {{ text-transform: none; }}
QTabBar::tab {{ text-transform: none; }}
QDockWidget {{ text-transform: none; }}
QHeaderView::section {{ text-transform: none; }}
QTreeView::indicator {{ width: 22px; height: 22px; }}
QTreeView::indicator:checked {{ image: url(icon:/primary/checkbox_checked.svg); }}
QTreeView::indicator:unchecked {{ image: url(icon:/primary/checkbox_unchecked.svg); }}
QTreeView::indicator:disabled {{ image: url(icon:/disabled/checkbox_unchecked.svg); }}
"""


def _glass_qss(p: Palette) -> str:
    """Verre : le dégradé est peint par la fenêtre, les conteneurs le laissent voir, les panneaux le voilent."""
    a, b, c = GLASS_STOPS
    panel = "rgba(255, 255, 255, 0.58)"     # panneau : assez opaque pour garder le texte à plus de 7:1
    field = "rgba(255, 255, 255, 0.78)"     # champs et listes : plus opaques, on y lit et on y écrit
    edge = "rgba(255, 255, 255, 0.95)"      # liseré clair, le « bord de verre »
    return f"""
QMainWindow, QDialog {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {a}, stop:0.5 {b}, stop:1 {c});
}}
QWidget#centralWidget, QStackedWidget, QSplitter, QScrollArea, QScrollArea > QWidget > QWidget,
QFrame#welcome, QScrollArea#welcomeScroll, QWidget#welcomeContent, QScrollArea#canvasScroll, QWidget#canvasInner,
QDockWidget, QDockWidget > QWidget, QTabWidget, QTabWidget > QWidget, QGroupBox, QLabel, QCheckBox, QRadioButton,
QToolBar, QStatusBar, QMenuBar, QWizardPage, QWizard > QWidget, QDialog > QWidget#qt_scrollarea_viewport {{
    background: transparent;
}}
QFrame#stageCard, QFrame#projectBar, QPushButton#startCard, QTabWidget::pane, QGroupBox {{
    background: {panel};
    border: 1px solid {edge};
    border-radius: 18px;
}}
QFrame#projectBar {{ border-radius: 0px; border-left: none; border-right: none; border-top: none; }}
QFrame#stageCard[dropState="ok"] {{ border: 2px solid {p.primary}; background: {field}; }}
QFrame#stageCard[dropState="no"] {{ border: 1px dashed {p.border}; background: rgba(255, 255, 255, 0.30); }}
QPushButton#startCard[recommended="true"] {{ border: 2px solid {p.primary}; }}
QPushButton#startCard:hover {{ border-color: {p.primary}; background: {field}; }}
QFrame#nextStep {{ background: rgba(255, 255, 255, 0.45); border-bottom: 1px solid {edge}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox, QTreeView, QTreeWidget, QListView,
QTableView, QTableWidget {{
    background: {field};
    border: 1px solid {edge};
    border-radius: 10px;
    color: {p.text};
}}
QListWidget#stageList {{ background: transparent; border: none; }}
QHeaderView::section {{ background: rgba(255, 255, 255, 0.55); color: {p.text}; border: none; }}
QPushButton {{
    background: {panel};
    border: 1px solid {edge};
    border-radius: 14px;
    color: {p.primary};
}}
QPushButton:hover {{ background: {field}; }}
QPushButton:disabled {{ color: {p.text_muted}; background: rgba(255, 255, 255, 0.30); }}
QPushButton:flat {{ background: transparent; border: none; }}
QToolBar QToolButton {{
    background: {panel};
    border: 1px solid {edge};
    border-radius: 14px;
    color: {p.text};
}}
QToolBar QToolButton:hover {{ background: {field}; }}
QToolBar QToolButton:disabled {{ color: {p.text_muted}; background: rgba(255, 255, 255, 0.30); }}
QToolButton#filtersToggle {{ background: transparent; }}
QMenu {{ background: rgba(248, 251, 255, 0.97); border: 1px solid {edge}; border-radius: 10px; color: {p.text}; }}
QMenuBar::item {{ background: transparent; color: {p.text}; }}
QTabBar::tab {{ background: transparent; color: {p.text}; }}
QToolTip {{ background: #14202c; color: #ffffff; border: none; border-radius: 6px; }}
QLabel[chip="true"] {{ background: rgba(255, 255, 255, 0.70); border: 1px solid {edge}; }}
"""


def _theme_file(p: Palette) -> Path:
    return THEMES_DIR / {"sombre": "devops_dark.xml", "verre": "devops_glass.xml"}.get(p.name, "devops_light.xml")


def palette_of(name: str | bool) -> Palette:
    """Palette d'un thème ; un booléen désigne l'ancien réglage « sombre »."""
    if isinstance(name, bool):
        return DARK if name else LIGHT
    return THEMES.get(name, LIGHT)


def apply(app: QApplication, name: str | bool = "clair", text_scale: float | None = None) -> Palette:
    """Applique le thème Material ; retourne la palette utilisée pour le dessin."""
    global _current, _scale
    import qt_material  # importé après PySide6, comme l'exige qt-material

    _current = palette_of(name)
    dark = _current.dark
    if text_scale is not None:
        _scale = min(TEXT_SCALES, key=lambda s: abs(s - text_scale))
    font = app.font()
    font.setPointSizeF(10 * _scale)
    app.setFont(font)
    extra = {"density_scale": "-1", "font_family": "Roboto, Inter, DejaVu Sans", "font_size": f"{px(13)}px",
             # couleurs des boutons « success », « danger », « warning » : celles de qt-material (#17a2b8…)
             # n'atteignent pas 4,5:1 sur fond clair
             "success": _current.primary, "danger": _current.blocking, "warning": _current.warning}
    qt_material.apply_stylesheet(app, theme=str(_theme_file(_current)), invert_secondary=not dark, extra=extra)
    app.setStyleSheet(app.styleSheet() + _extra_qss(_current) + (_glass_qss(_current) if _current.glass else ""))
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
