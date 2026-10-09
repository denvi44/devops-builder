"""Vue « Ports et exposition » : ports de l'application et des briques, par environnement."""

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
from ..model import Project
from ..ports import conflicts, env_offset, port_plan, shared_hosts
from . import theme
from .widgets import icon, muted

COLUMNS = ["Environnement", "Composant", "Port publié", "Port du conteneur", "Usage", "Exposition"]


class PortsDialog(QDialog):
    def __init__(self, project: Project, catalog: Catalog, parent: QWidget | None = None,
                 edit_environments: Callable[[], Project] | None = None):
        super().__init__(parent)
        self.project, self.catalog = project, catalog
        self.edit_environments = edit_environments
        self.setWindowTitle("Ports et exposition")
        self.resize(1080, 560)
        lay = QVBoxLayout(self)
        self.intro = muted("")
        lay.addWidget(self.intro)
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
        self.tree.setAccessibleName("Ports par environnement")
        header = self.tree.header()
        for i in range(len(COLUMNS)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tree, 1)
        self.summary = muted("")
        lay.addWidget(self.summary)
        row = QHBoxLayout()
        if edit_environments is not None:
            envs = QPushButton(icon("mdi6.server-network"), "Hôtes et décalages…")
            envs.setToolTip("Paramètres du projet › Environnements")
            envs.clicked.connect(self._edit)
            row.addWidget(envs)
        row.addStretch(1)
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        self.plan = port_plan(self.project, self.catalog)
        shared = shared_hosts(self.project)
        if shared:
            text = " ; ".join(f"hôte « {h} » partagé par " + ", ".join(
                f"{e.display} (+{env_offset(self.project, e)})" for e in envs) for h, envs in shared.items())
            self.intro.setText(f"Ports décalés sur les hôtes partagés : {text}.")
        elif self.project.target in ("docker-host", "vm"):
            self.intro.setText("Chaque environnement est supposé sur son propre hôte Docker. Si plusieurs partagent "
                               "une machine, indiquez le même « Hôte Docker partagé » : leurs ports seront décalés.")
        else:
            self.intro.setText("Sur Kubernetes, chaque environnement a son espace de noms : les ports des Services "
                               "ne peuvent pas entrer en conflit.")
        self._fill()

    def _fill(self) -> None:
        pal = theme.current()
        env_id = self.env.currentData()
        self.tree.clear()
        shown = [e for e in self.plan if not env_id or e.env_id == env_id]
        for e in shown:
            item = QTreeWidgetItem([e.env, e.component, str(e.host_port) if e.host_port is not None else "—",
                                    str(e.container_port), e.usage, e.exposure])
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if e.variable:
                item.setToolTip(2, f"Variable {e.variable} (deploy/env/{e.env_id}.env)")
            if e.conflict:
                for col in range(len(COLUMNS)):
                    item.setForeground(col, theme.qcolor(pal.blocking))
                    item.setToolTip(col, e.conflict)
                item.setIcon(2, icon("mdi6.alert-octagon", pal.blocking))
            self.tree.addTopLevelItem(item)
        published = sum(1 for e in shown if e.host_port is not None)
        bad = conflicts(shown)
        text = f"{len(shown)} port(s), dont {published} publié(s) sur un hôte"
        text += f" — {len(bad)} en conflit (voir les diagnostics R39)." if bad else " — aucun conflit."
        self.summary.setText(text)

    def _edit(self) -> None:
        if self.edit_environments is not None:
            self.project = self.edit_environments()
            self.refresh()
