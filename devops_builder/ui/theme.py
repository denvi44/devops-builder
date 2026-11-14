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
GLASS_STOPS = ("#b4cdf3", "#cfc2f1", "#aedfcb")
GLASS = Palette(False, "#004a40", "#3d8f81", "#dcd9f6", "#cfc2f1", "#c2d0e4", "#14202c", "#3c4856",
                blocking="#861a14", warning="#722b00", info="#093f87", ok="#174d1b", name="verre", glass=True)
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
    """Verre : le dégradé est peint par la fenêtre, les conteneurs le laissent voir, les panneaux le voilent.

    Les boutons déclarent tous leurs états (survol, appui, coché, focus) : sinon les règles de qt-material
    (bordures de 12 px colorées par état) reprennent la main au survol et déforment le bouton.
    """
    a, b, c = GLASS_STOPS
    panel = "rgba(246, 249, 255, 0.46)"     # panneau : voile bleuté, ni blanc franc ni opaque
    field = "rgba(248, 251, 255, 0.72)"     # champs et listes : plus opaques, on y lit et on y écrit
    edge = "rgba(255, 255, 255, 0.70)"      # liseré clair, le « bord de verre »
    lift = "rgba(255, 255, 255, 0.78)"      # bouton survolé : le verre s'éclaircit
    press = _rgba(p.primary, 0.22)          # bouton appuyé ou coché : teinte de la couleur principale
    hov_edge = p.primary
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
QFrame#stageCard, QFrame#projectBar, QPushButton#startCard, QTabWidget::pane, QGroupBox, QWidget#fixesPanel {{
    background: {panel};
    border: 1px solid {edge};
    border-radius: 18px;
}}
QFrame#projectBar {{ border-radius: 0px; border-left: none; border-right: none; border-top: none; }}
QFrame#stageCard[dropState="ok"] {{ border: 2px solid {p.primary}; background: {field}; }}
QFrame#stageCard[dropState="no"] {{ border: 1px dashed {p.text_muted}; background: rgba(255, 255, 255, 0.22); }}
QPushButton#startCard[recommended="true"] {{ border: 2px solid {p.primary}; }}
QPushButton#startCard:hover, QPushButton#startCard:focus {{ border: 2px solid {hov_edge}; background: {lift}; }}
QPushButton#startCard:pressed {{ border: 2px solid {hov_edge}; background: {press}; }}
QFrame#nextStep {{ background: rgba(255, 255, 255, 0.34); border-bottom: 1px solid {edge}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox, QTreeView, QTreeWidget, QListView,
QTableView, QTableWidget {{
    background: {field};
    border: 1px solid {edge};
    border-radius: 10px;
    color: {p.text};
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{ background: {_rgba(p.primary, 0.14)}; color: {p.text}; }}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected,
QTreeView::item:selected:hover {{ background: {_rgba(p.primary, 0.30)}; color: {p.text}; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border: 1px solid {hov_edge}; background: {lift}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {hov_edge}; }}
QListWidget#stageList {{ background: transparent; border: none; }}
QHeaderView, QTableView QTableCornerButton::section {{ background: transparent; border: none; }}
QHeaderView::section {{ background: rgba(255, 255, 255, 0.30); color: {p.text}; border: none; padding: 4px 8px; }}
QPushButton, QPushButton:hover, QPushButton:pressed, QPushButton:focus, QPushButton:checked {{
    border: 1px solid {edge};
    border-radius: 14px;
    padding: 4px 14px;
    margin: 0px;
    color: {p.primary};
}}
QPushButton {{ background: {panel}; }}
QPushButton:hover {{ background: {lift}; border: 1px solid {hov_edge}; }}
QPushButton:focus {{ background: {lift}; border: 2px solid {hov_edge}; }}
QPushButton:pressed, QPushButton:checked {{ background: {press}; border: 1px solid {hov_edge}; }}
QPushButton:disabled {{ color: {p.text_muted}; background: rgba(255, 255, 255, 0.22); border: 1px solid {edge}; }}
QPushButton:flat, QPushButton:flat:hover, QPushButton:flat:focus {{ background: transparent; border: none; }}
QToolBar QToolButton, QToolBar QToolButton:hover, QToolBar QToolButton:pressed, QToolBar QToolButton:checked,
QToolBar QToolButton:focus {{
    border: 1px solid {edge};
    border-left: 1px solid {edge};
    border-right: 1px solid {edge};
    border-radius: 14px;
    padding: 4px 12px;
    margin: 3px 2px;
    color: {p.text};
}}
QToolBar QToolButton {{ background: {panel}; }}
QToolBar QToolButton:hover {{ background: {lift}; border: 1px solid {hov_edge}; }}
QToolBar QToolButton:focus {{ background: {lift}; border: 2px solid {hov_edge}; }}
QToolBar QToolButton:pressed, QToolBar QToolButton:checked {{ background: {press}; border: 1px solid {hov_edge}; }}
QToolBar QToolButton:disabled {{ color: {p.text_muted}; background: rgba(255, 255, 255, 0.22); border: 1px solid {edge}; }}
QToolButton#filtersToggle, QToolButton#filtersToggle:hover {{ background: transparent; border: none; }}
QMenu {{ background: rgba(244, 248, 255, 0.97); border: 1px solid {edge}; border-radius: 10px; color: {p.text}; }}
QMenu::item:selected {{ background: {_rgba(p.primary, 0.20)}; color: {p.text}; }}
QMenuBar::item {{ background: transparent; color: {p.text}; }}
QMenuBar::item:selected {{ background: {_rgba(p.primary, 0.20)}; color: {p.text}; border-radius: 8px; }}
QTabBar::tab {{ background: transparent; color: {p.text}; }}
QTabBar::tab:hover {{ background: {_rgba(p.primary, 0.14)}; }}
QToolTip {{ background: #14202c; color: #ffffff; border: none; border-radius: 6px; }}
QLabel[chip="true"] {{ background: rgba(255, 255, 255, 0.50); border: 1px solid {edge}; }}
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
