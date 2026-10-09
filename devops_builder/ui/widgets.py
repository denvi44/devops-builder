"""Petits composants Material : icônes, puces, en-têtes de section."""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QWidget

from . import theme

STAGE_ICONS = {
    "source": "mdi6.source-branch",
    "build": "mdi6.hammer-wrench",
    "test": "mdi6.test-tube",
    "security": "mdi6.shield-check",
    "artifacts": "mdi6.package-variant",
    "infrastructure": "mdi6.server",
    "deploy": "mdi6.rocket-launch",
    "platform": "mdi6.layers",
    "observability": "mdi6.chart-line",
}
KIND_ICONS = {"tool": "mdi6.puzzle", "service": "mdi6.cloud-outline", "provider": "mdi6.cloud"}
SEVERITY_ICONS = {"bloquant": "mdi6.alert-octagon", "avertissement": "mdi6.alert", "info": "mdi6.information"}


def icon(name: str, color: str | None = None) -> QIcon:
    try:
        import qtawesome as qta
        return qta.icon(name, color=color or theme.current().text)
    except Exception:  # icône inconnue ou qtawesome absent : pas d'icône plutôt qu'un plantage
        return QIcon()


def chip(text: str, primary: bool = False, tooltip: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("chip", "primary" if primary else "true")
    if tooltip:
        lbl.setToolTip(tooltip)
    lbl.setAccessibleName(text)
    lbl.setFixedHeight(24)
    return lbl


def clear_layout(layout: QLayout) -> None:
    """Vide un layout en détachant immédiatement ses widgets (pas de superposition visuelle)."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def plain(text: str) -> str:
    """Texte de bouton ou de case : « & » y désigne un raccourci clavier, on l'affiche tel quel."""
    return text.replace("&", "&&")


def section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("sectionTitle")
    return lbl


def muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("muted")
    lbl.setWordWrap(True)
    return lbl


class FlowRow(QWidget):
    """Rangée de puces qui passe à la ligne (simple : retour toutes les N puces)."""

    def __init__(self, labels: list[QLabel], per_row: int = 3, parent: QWidget | None = None):
        super().__init__(parent)
        from PySide6.QtWidgets import QVBoxLayout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        rows: list[QHBoxLayout] = []
        for i, lbl in enumerate(labels):
            if i % per_row == 0:
                row = QHBoxLayout()
                row.setSpacing(4)
                outer.addLayout(row)
                rows.append(row)
            rows[-1].addWidget(lbl)
        for row in rows:
            row.addStretch(1)
