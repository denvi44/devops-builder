"""Vue « Données » : chaque base, par environnement — mode, version, taille, connexion, secret, sauvegarde."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..catalog import Catalog
from ..datainfo import DbRow, rows
from ..model import Project
from ..rules import Action, Diagnostic, RuleEngine
from . import theme
from .widgets import icon, muted

COLUMNS = ["Environnement", "Base", "Mode", "Version", "Taille", "Connexion", "Mot de passe / URL", "Sauvegarde"]
DATA_RULES = ("R40", "R41", "R42", "R43", "R46", "R47")


class DataDialog(QDialog):
    """Tableau des bases ; une ligne avec un avertissement propose sa correction."""

    def __init__(self, project: Project, catalog: Catalog, engine: RuleEngine, parent: QWidget | None = None,
                 apply_fix: Callable[[Action], Project] | None = None,
                 focus_brick: Callable[[str], None] | None = None):
        super().__init__(parent)
        self.project, self.catalog, self.engine = project, catalog, engine
        self.apply_fix, self.focus_brick = apply_fix, focus_brick
        self.setWindowTitle("Données")
        self.resize(1180, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Ce que deviennent les bases du projet dans chaque environnement : mode d'hébergement, "
                            "variable lue par l'application, source du mot de passe et sauvegarde."))
        top = QHBoxLayout()
        self.env = QComboBox()
        self.env.setAccessibleName("Filtrer par environnement")
        self.env.addItem("Tous les environnements", "")
        for e in project.environments:
            self.env.addItem(e.display, e.id)
        self.env.currentIndexChanged.connect(self._fill)
        top.addWidget(self.env)
        top.addStretch(1)
        lay.addLayout(top)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.setAccessibleName("Bases par environnement")
        header = self.tree.header()
        for i in range(len(COLUMNS)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.tree.currentItemChanged.connect(self._current)
        self.tree.itemDoubleClicked.connect(self._open)
        lay.addWidget(self.tree, 1)
        self.detail = muted("")
        self.detail.setWordWrap(True)
        lay.addWidget(self.detail)
        row = QHBoxLayout()
        self.fix = QPushButton(icon("mdi6.auto-fix"), "Corriger")
        self.fix.setEnabled(False)
        self.fix.clicked.connect(self._apply)
        row.addWidget(self.fix)
        self.show_brick = QPushButton(icon("mdi6.cursor-default-click-outline"), "Afficher la brique")
        self.show_brick.setEnabled(False)
        self.show_brick.clicked.connect(lambda: self._open(self.tree.currentItem()))
        row.addWidget(self.show_brick)
        row.addStretch(1)
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        self.diagnostics: list[Diagnostic] = [d for d in self.engine.evaluate(self.project) if d.rule_id in DATA_RULES]
        self.rows = rows(self.project, self.catalog, self.diagnostics)
        self._fill()

    def _uid(self, row: DbRow) -> str:
        return next((b.uid for _, b in self.project.all_bricks() if b.tool == row.db_id), "")

    def _fill(self) -> None:
        pal = theme.current()
        env_id = self.env.currentData()
        self.tree.clear()
        shown = [r for r in self.rows if not env_id or r.env_id == env_id]
        for r in shown:
            item = QTreeWidgetItem([r.env, r.name, r.badge, r.version or "—", r.size or "—", r.connection, r.secret,
                                    r.backup])
            item.setData(0, Qt.ItemDataRole.UserRole, r)
            for col in range(2, len(COLUMNS)):
                item.setToolTip(col, item.text(col))  # texte entier quand la colonne est rognée
            if r.warnings:
                item.setIcon(1, icon("mdi6.alert", pal.warning))
                item.setToolTip(1, "\n".join(r.warnings))
                item.setData(1, Qt.ItemDataRole.AccessibleTextRole, f"{r.name}, {len(r.warnings)} avertissement(s)")
            self.tree.addTopLevelItem(item)
        warned = sum(1 for r in shown if r.warnings)
        if not self.rows:
            self.detail.setText("Aucune base dans le pipeline : ajoutez-en une depuis l'étape Données de la palette.")
        else:
            self.detail.setText(f"{len(shown)} ligne(s)" + (f", {warned} avec un avertissement : sélectionnez-la "
                                                             "pour le détail et la correction." if warned else "."))
        self.fix.setEnabled(False)

    def _row(self, item: QTreeWidgetItem | None) -> DbRow | None:
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def _action(self, row: DbRow) -> Action | None:
        uid = self._uid(row)
        for d in self.diagnostics:
            if uid in d.bricks and d.actions:
                return d.actions[0]
        return None

    def _current(self, item: QTreeWidgetItem | None, _previous=None) -> None:
        row = self._row(item)
        self.show_brick.setEnabled(row is not None and self.focus_brick is not None)
        if row is None:
            return
        action = self._action(row)
        self.fix.setEnabled(action is not None and self.apply_fix is not None)
        self.fix.setText(f"Corriger : {action.label}" if action else "Corriger")
        lines = [f"{row.name} ({row.env}) — {row.connection} ; {row.secret}."]
        lines += row.warnings
        self.detail.setText("\n".join(lines))

    def _apply(self) -> None:
        row = self._row(self.tree.currentItem())
        action = self._action(row) if row else None
        if action is None or self.apply_fix is None:
            return
        self.project = self.apply_fix(action)
        self.refresh()

    def _open(self, item: QTreeWidgetItem | None) -> None:
        row = self._row(item)
        if row is None or self.focus_brick is None:
            return
        uid = self._uid(row)
        if uid:
            self.focus_brick(uid)
            self.accept()
