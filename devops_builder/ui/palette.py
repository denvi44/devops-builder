"""Palette d'outils : recherche, filtres, glisser vers le canevas."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..catalog import Catalog
from ..model import STAGE_LABELS, STAGES, Tool
from . import theme
from .widgets import KIND_ICONS, STAGE_ICONS, icon

MIME_TOOL = "application/x-devops-tool"
MATURITY = [("", "Toutes maturités"), ("graduated", "CNCF graduated"), ("incubating", "CNCF incubating"),
            ("sandbox", "CNCF sandbox"), ("none", "Hors projets CNCF")]


class _Tree(QTreeWidget):
    dragStarted = Signal(str)
    dragFinished = Signal()

    def startDrag(self, actions):  # noqa: N802
        item = self.currentItem()
        tid = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not tid:
            return
        self.dragStarted.emit(tid)
        try:
            super().startDrag(actions)
        finally:
            self.dragFinished.emit()

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
    ficheRequested = Signal(str)  # créer une fiche (entrée du Landscape) ou modifier une fiche personnelle
    ficheDeleteRequested = Signal(str)

    def __init__(self, catalog: Catalog, parent: QWidget | None = None):
        super().__init__(parent)
        self.catalog = catalog
        self.target: str | None = None
        self.project = None
        self.reasons: dict[str, str] = {}

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
        self.compatible = QCheckBox("Adapté au projet")
        self.compatible.setToolTip("Masque les briques que le projet écarterait : cible, forge, licence, SecNumCloud, "
                                   "fournisseur cloud, rôle déjà tenu. Une recherche montre tout, en grisant ce qui ne "
                                   "convient pas.")
        self.compatible.setChecked(QSettings("DevOpsBuilder", "DevOpsBuilder").value("palette/adapted", True, type=bool))
        self.compatible.toggled.connect(
            lambda on: QSettings("DevOpsBuilder", "DevOpsBuilder").setValue("palette/adapted", on))
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
        self.tree.setAccessibleDescription("Entrée ou double-clic ajoute l'outil à son étape ; glisser vers une colonne ; "
                                           "menu contextuel pour créer ou modifier une fiche.")
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        lay.addWidget(self.tree, 1)

        self.count = QLabel()
        self.count.setWordWrap(True)
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

    def set_project(self, project) -> None:
        """Le projet courant détermine les briques proposées par défaut."""
        key = (project.target, project.license_policy, project.secnumcloud, frozenset(project.tool_ids()))
        self.project = project
        self.target = project.target
        if key != getattr(self, "_project_key", None):
            self._project_key = key
            self.refresh()

    def refresh(self) -> None:
        tools = self.catalog.search(
            text=self.search.text(),
            stage=self.stage.currentData() or None,
            include_uncurated=self.landscape.isChecked(),
            oss_only=self.oss.isChecked(),
            maturity=self.maturity.currentData() or None,
        )
        from ..compat import adapted
        self.reasons = adapted(tools, self.project, self.catalog)[1] if self.project is not None else {}
        hidden = 0
        if self.compatible.isChecked() and not self.search.text().strip():
            hidden = sum(1 for t in tools if t.id in self.reasons)
            tools = [t for t in tools if t.id not in self.reasons]
        self.tree.setUpdatesEnabled(False)
        # garder les groupes ouverts et la position de défilement d'un rafraîchissement à l'autre
        opened = {self.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole + 1)
                  for i in range(self.tree.topLevelItemCount()) if self.tree.topLevelItem(i).isExpanded()}
        scroll = self.tree.verticalScrollBar().value()
        first = self.tree.topLevelItemCount() == 0
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
            g.setData(0, Qt.ItemDataRole.UserRole + 1, sid)
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
            why = self.reasons.get(t.id)
            if why:
                item.setForeground(0, theme.qcolor(pal.text_muted))
                item.setText(0, item.text(0) + "  ⊘")
                item.setToolTip(0, f"<b>Écarté pour ce projet :</b> {why}<br>" + self._tooltip(t))
            groups[t.stage].addChild(item)
        for sid, _ in STAGES:
            g = groups[sid]
            if g.childCount():
                g.setText(0, f"{g.text(0)}  ({g.childCount()})")
                self.tree.addTopLevelItem(g)
                auto = bool(self.search.text()) or self.stage.currentData() == sid or len(tools) < 60
                g.setExpanded(auto if (first or self.search.text()) else (sid in opened or auto))
        self.tree.setUpdatesEnabled(True)
        if not first and not self.search.text():
            self.tree.verticalScrollBar().setValue(scroll)
        curated = sum(1 for t in tools if t.curated)
        mine = sum(1 for t in tools if t.origin == "utilisateur")
        text = f"{len(tools)} outils · {curated} fiches vérifiées" + (f" dont {mine} personnelle(s)" if mine else "")
        if hidden:
            text += f" · {hidden} masqué(s), inadapté(s) au projet"
        self.count.setText(text)
        self.count.setToolTip("Décocher « Adapté au projet », ou rechercher un nom, pour voir les briques masquées."
                              if hidden else "")

    @staticmethod
    def _label(t: Tool) -> str:
        badge = ""
        if t.landscape and t.landscape.maturity in ("graduated", "incubating"):
            badge = "  ◆"
        if t.lifecycle != "active":
            badge += "  ⚠"
        if t.origin == "utilisateur":
            badge += "  ✎"
        elif t.corrections:
            badge += "  ✱"
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
        meta.append("Étapes : " + ", ".join(STAGE_LABELS[s] for s in t.allowed_stages))
        if not t.curated:
            meta.append("Fiche non vérifiée — clic droit pour créer une fiche")
        if t.origin == "utilisateur":
            meta.append("Fiche personnelle")
        if t.corrections:
            meta.append("Corrigée localement : " + ", ".join(t.corrections))
        lines.append(" · ".join(meta))
        if t.lifecycle_note:
            lines.append(f"⚠ {t.lifecycle_note}")
        return "<br>".join(lines)

    def _context_menu(self, pos: QPoint) -> None:
        item = self.tree.itemAt(pos)
        tid = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        tool = self.catalog.get(tid) if tid else None
        if tool is None:
            return
        menu = self.context_menu(tool)
        if not menu.isEmpty():
            menu.exec(self.tree.viewport().mapToGlobal(pos))

    def context_menu(self, tool: Tool) -> QMenu:
        menu = QMenu(self)
        if not tool.curated:
            menu.addAction(icon("mdi6.file-plus-outline"), "Créer une fiche à partir de cette entrée…",
                           lambda: self.ficheRequested.emit(tool.id))
        elif tool.origin == "utilisateur":
            menu.addAction(icon("mdi6.pencil-outline"), "Modifier la fiche…", lambda: self.ficheRequested.emit(tool.id))
            menu.addAction(icon("mdi6.delete-outline"), "Supprimer la fiche", lambda: self.ficheDeleteRequested.emit(tool.id))
        return menu

    def _activated(self, item: QTreeWidgetItem) -> None:
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        if tid:
            self.toolActivated.emit(tid)

    def _selected(self, item: QTreeWidgetItem | None) -> None:
        if item is not None:
            tid = item.data(0, Qt.ItemDataRole.UserRole)
            if tid:
                self.toolSelected.emit(tid)
