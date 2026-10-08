"""Palette d'outils : recherche, filtres, glisser vers le canevas."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..catalog import Catalog
from ..model import STAGES, Tool
from . import theme
from .widgets import KIND_ICONS, STAGE_ICONS, icon

MIME_TOOL = "application/x-devops-tool"
MATURITY = [("", "Toutes maturités"), ("graduated", "CNCF graduated"), ("incubating", "CNCF incubating"),
            ("sandbox", "CNCF sandbox"), ("none", "Hors projets CNCF")]


class _Tree(QTreeWidget):
    def mimeData(self, items):  # noqa: N802 (API Qt)
        data = QMimeData()
        ids = [i.data(0, Qt.ItemDataRole.UserRole) for i in items if i.data(0, Qt.ItemDataRole.UserRole)]
        if ids:
            data.setData(MIME_TOOL, ids[0].encode())
            data.setText(ids[0])
        return data

    def mimeTypes(self):  # noqa: N802
        return [MIME_TOOL]


class PaletteWidget(QWidget):
    toolActivated = Signal(str)   # double-clic / Entrée : ajouter à l'étape par défaut
    toolSelected = Signal(str)    # sélection : afficher la fiche

    def __init__(self, catalog: Catalog, parent: QWidget | None = None):
        super().__init__(parent)
        self.catalog = catalog
        self.target: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un outil, un rôle…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Rechercher dans le catalogue")
        lay.addWidget(self.search)

        self.stage = QComboBox()
        self.stage.addItem("Toutes les étapes", "")
        for sid, label in STAGES:
            self.stage.addItem(icon(STAGE_ICONS[sid]), label, sid)
        self.stage.setAccessibleName("Filtrer par étape")
        self.maturity = QComboBox()
        for key, label in MATURITY:
            self.maturity.addItem(label, key)
        self.maturity.setAccessibleName("Filtrer par maturité CNCF")
        row = QHBoxLayout()
        row.addWidget(self.stage, 1)
        row.addWidget(self.maturity, 1)
        lay.addLayout(row)

        self.oss = QCheckBox("Open source uniquement")
        self.compatible = QCheckBox("Compatible avec la cible")
        self.compatible.setToolTip("Masque les outils réservés à Kubernetes quand la cible n'en a pas.")
        self.landscape = QCheckBox("Inclure tout le Landscape (non vérifié)")
        self.landscape.setToolTip("Ajoute les ~1 000 entrées du CNCF Landscape sans fiche de compatibilité.")
        for cb in (self.oss, self.compatible, self.landscape):
            lay.addWidget(cb)

        self.tree = _Tree()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setAccessibleName("Catalogue d'outils")
        self.tree.setAccessibleDescription("Entrée ou double-clic ajoute l'outil à son étape ; glisser vers une colonne.")
        lay.addWidget(self.tree, 1)

        self.count = QLabel()
        self.count.setObjectName("muted")
        lay.addWidget(self.count)

        self.search.textChanged.connect(self.refresh)
        for w in (self.stage, self.maturity):
            w.currentIndexChanged.connect(self.refresh)
        for cb in (self.oss, self.compatible, self.landscape):
            cb.toggled.connect(self.refresh)
        self.tree.itemActivated.connect(self._activated)
        self.tree.currentItemChanged.connect(self._selected)
        self.refresh()

    # ------------------------------------------------------------------
    def set_target(self, target: str) -> None:
        self.target = target
        if self.compatible.isChecked():
            self.refresh()

    def refresh(self) -> None:
        tools = self.catalog.search(
            text=self.search.text(),
            stage=self.stage.currentData() or None,
            include_uncurated=self.landscape.isChecked(),
            oss_only=self.oss.isChecked(),
            maturity=self.maturity.currentData() or None,
            target=self.target if self.compatible.isChecked() else None,
        )
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        pal = theme.current()
        for sid, label in STAGES:
            g = QTreeWidgetItem([label])
            g.setIcon(0, icon(STAGE_ICONS[sid], pal.primary))
            g.setFlags(Qt.ItemFlag.ItemIsEnabled)
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            groups[sid] = g
        for t in tools:
            item = QTreeWidgetItem([self._label(t)])
            item.setData(0, Qt.ItemDataRole.UserRole, t.id)
            item.setToolTip(0, self._tooltip(t))
            color = pal.text if t.curated else pal.text_muted
            item.setIcon(0, icon(KIND_ICONS.get(t.kind, "mdi6.puzzle"), color))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
            if not t.curated:
                item.setForeground(0, theme.qcolor(pal.text_muted))
            groups[t.stage].addChild(item)
        for sid, _ in STAGES:
            g = groups[sid]
            if g.childCount():
                g.setText(0, f"{g.text(0)}  ({g.childCount()})")
                self.tree.addTopLevelItem(g)
                g.setExpanded(bool(self.search.text()) or self.stage.currentData() == sid or len(tools) < 60)
        self.tree.setUpdatesEnabled(True)
        curated = sum(1 for t in tools if t.curated)
        self.count.setText(f"{len(tools)} outils · {curated} fiches vérifiées")

    @staticmethod
    def _label(t: Tool) -> str:
        badge = ""
        if t.landscape and t.landscape.maturity in ("graduated", "incubating"):
            badge = "  ◆"
        if t.lifecycle != "active":
            badge += "  ⚠"
        return t.name + badge

    @staticmethod
    def _tooltip(t: Tool) -> str:
        lines = [f"<b>{t.name}</b>"]
        if t.description:
            lines.append(t.description)
        meta = [f"Licence : {t.license}"]
        if t.landscape and t.landscape.maturity:
            meta.append(f"CNCF : {t.landscape.maturity}")
        if t.provider:
            meta.append(f"Fournisseur : {t.provider}")
        if t.kubernetes_only:
            meta.append("Kubernetes obligatoire")
        if not t.curated:
            meta.append("Fiche non vérifiée")
        lines.append(" · ".join(meta))
        if t.lifecycle_note:
            lines.append(f"⚠ {t.lifecycle_note}")
        return "<br>".join(lines)

    def _activated(self, item: QTreeWidgetItem) -> None:
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        if tid:
            self.toolActivated.emit(tid)

    def _selected(self, item: QTreeWidgetItem | None) -> None:
        if item is not None:
            tid = item.data(0, Qt.ItemDataRole.UserRole)
            if tid:
                self.toolSelected.emit(tid)
