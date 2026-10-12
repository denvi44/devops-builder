# SPDX-License-Identifier: Apache-2.0
"""Panneau des diagnostics : liste triée par gravité et corrections en un clic."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..model import Severity
from ..rules import Action, Diagnostic
from . import theme
from .widgets import SEVERITY_ICONS, clear_layout, icon, muted, plain, section_title


class DiagnosticsPanel(QWidget):
    brickFocused = Signal(str)
    actionRequested = Signal(object)  # Action

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._diags: list[Diagnostic] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)

        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.summary)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Gravité", "Règle", "Message"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 140)
        self.tree.setColumnWidth(1, 72)
        self.tree.setAlternatingRowColors(True)
        self.tree.setAccessibleName("Diagnostics de compatibilité")
        self.tree.currentItemChanged.connect(self._current)
        self.tree.itemActivated.connect(self._activated)
        split.addWidget(self.tree)

        self.fixes = QWidget()
        self.fixes_lay = QVBoxLayout(self.fixes)
        self.fixes_lay.setContentsMargins(8, 0, 0, 0)
        self.fixes_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        split.addWidget(self.fixes)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        self._show_fixes(None)

    def set_diagnostics(self, diags: list[Diagnostic]) -> None:
        self._diags = diags
        pal = theme.current()
        counts = {s: sum(1 for d in diags if d.severity is s) for s in Severity}
        parts = []
        for s in Severity:
            parts.append(f'<span style="color:{pal.severity(s.value)}; font-weight:600">{counts[s]} {s.label.lower()}{"s" if counts[s] > 1 and s is not Severity.INFO else ""}</span>')
        state = ("<b>Génération bloquée</b>" if counts[Severity.BLOCKING]
                 else f'<span style="color:{pal.ok}"><b>Prêt à générer</b></span>')
        self.summary.setText(" · ".join(parts) + " — " + state)
        self.tree.clear()
        for i, d in enumerate(diags):
            item = QTreeWidgetItem([d.severity.label, d.rule_id, d.message])
            item.setIcon(0, icon(SEVERITY_ICONS[d.severity.value], pal.severity(d.severity.value)))
            item.setToolTip(2, f"{d.family_label} — {d.message}")
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            self.tree.addTopLevelItem(item)
        self._show_fixes(None)

    def _diag_of(self, item: QTreeWidgetItem | None) -> Diagnostic | None:
        if item is None:
            return None
        i = item.data(0, Qt.ItemDataRole.UserRole)
        return self._diags[i] if i is not None and i < len(self._diags) else None

    def _current(self, item: QTreeWidgetItem | None) -> None:
        d = self._diag_of(item)
        self._show_fixes(d)
        if d and d.bricks:
            self.brickFocused.emit(d.bricks[0])

    def _activated(self, item: QTreeWidgetItem) -> None:
        d = self._diag_of(item)
        if d and d.actions:
            self.actionRequested.emit(d.actions[0])

    def _show_fixes(self, d: Diagnostic | None) -> None:
        clear_layout(self.fixes_lay)
        if d is None:
            self.fixes_lay.addWidget(section_title("Corrections"))
            self.fixes_lay.addWidget(muted("Sélectionnez un diagnostic pour voir les corrections proposées."))
            return
        self.fixes_lay.addWidget(section_title(f"{d.rule_id} · {d.family_label}"))
        self.fixes_lay.addWidget(muted(d.message))
        if not d.actions:
            self.fixes_lay.addWidget(muted("Aucune correction automatique."))
        for a in d.actions:
            self.fixes_lay.addWidget(self._action_button(a))

    def _action_button(self, a: Action) -> QPushButton:
        names = {"add_brick": "mdi6.plus-circle-outline", "remove_bricks": "mdi6.minus-circle-outline",
                 "replace_brick": "mdi6.swap-horizontal", "set_project": "mdi6.cog-outline"}
        b = QPushButton(icon(names.get(a.op, "mdi6.wrench"), theme.current().primary), plain(a.label))
        b.setToolTip("Appliquer cette correction (annulable avec Ctrl+Z)")
        b.clicked.connect(lambda: self.actionRequested.emit(a))
        return b
