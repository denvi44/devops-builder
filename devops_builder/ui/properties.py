"""Panneau des propriétés : fiche de l'outil et paramètres de la brique."""

from __future__ import annotations

from typing import Any

import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..catalog import Catalog
from ..model import STAGE_LABELS, BrickInstance, Tool
from . import theme
from .widgets import FlowRow, chip, icon, muted, section_title

HOSTING = {"kubernetes": "Kubernetes", "docker-host": "Hôte Docker", "vm": "VM", "saas": "SaaS",
           "ci": "Job CI", "cli": "CLI"}
LIFECYCLE = {"active": "Actif", "maintenance-ended": "Maintenance arrêtée", "archived": "Archivé",
             "discontinued": "Arrêté"}


class PropertiesPanel(QScrollArea):
    paramsChanged = Signal(str, dict)   # uid, params
    removeRequested = Signal(str)
    addRequested = Signal(str)          # tool_id (fiche affichée depuis la palette)

    def __init__(self, catalog: Catalog, parent: QWidget | None = None):
        super().__init__(parent)
        self.catalog = catalog
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self._uid: str | None = None
        self._tool_id: str | None = None
        self._loading = False
        self.show_empty()

    def _container(self) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        return w, lay

    def show_empty(self) -> None:
        self._uid = self._tool_id = None
        w, lay = self._container()
        lay.addWidget(section_title("Aucune sélection"))
        lay.addWidget(muted("Sélectionnez une brique du pipeline ou un outil du catalogue pour afficher sa fiche."))
        self.setWidget(w)

    def show_tool(self, tool: Tool, brick: BrickInstance | None = None) -> None:
        self._uid = brick.uid if brick else None
        self._tool_id = tool.id
        pal = theme.current()
        w, lay = self._container()

        head = QHBoxLayout()
        title = QLabel(tool.name)
        title.setObjectName("heroTitle")
        title.setWordWrap(True)
        head.addWidget(title, 1)
        lay.addLayout(head)
        kind = {"tool": "Outil", "service": "Service managé", "provider": "Fournisseur cloud"}[tool.kind]
        lay.addWidget(muted(f"{kind} · étape {STAGE_LABELS.get(tool.stage, tool.stage)}"))
        if tool.description:
            d = QLabel(tool.description)
            d.setWordWrap(True)
            lay.addWidget(d)

        chips = [chip(tool.license, tooltip="Licence")]
        if tool.landscape and tool.landscape.maturity:
            chips.append(chip(f"CNCF {tool.landscape.maturity}", primary=True))
        if tool.lifecycle != "active":
            chips.append(chip(LIFECYCLE[tool.lifecycle]))
        if not tool.curated:
            chips.append(chip("Fiche non vérifiée"))
        if tool.dev_only:
            chips.append(chip("Développement uniquement"))
        lay.addWidget(FlowRow(chips, per_row=3))

        if tool.lifecycle_note:
            note = QLabel(f"⚠ {tool.lifecycle_note}")
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {pal.warning};")
            lay.addWidget(note)

        if tool.roles:
            lay.addWidget(section_title("Rôles"))
            lay.addWidget(FlowRow([chip(r) for r in tool.roles], per_row=3))
        lay.addWidget(section_title("Étapes possibles"))
        lay.addWidget(FlowRow([chip(STAGE_LABELS[s], primary=(s == tool.stage)) for s in tool.allowed_stages],
                              per_row=2))
        lay.addWidget(section_title("S'exécute sur"))
        lay.addWidget(FlowRow([chip(HOSTING.get(h, h)) for h in tool.hosting], per_row=3))
        if tool.provides or tool.requires:
            lay.addWidget(section_title("Capacités"))
            if tool.provides:
                lay.addWidget(muted("Fournit : " + ", ".join(tool.provides)))
            if tool.requires:
                lay.addWidget(muted("Requiert : " + ", ".join(tool.requires)))
        if tool.provider:
            prov = self.catalog.get(tool.provider)
            lay.addWidget(muted(f"Fournisseur : {prov.name if prov else tool.provider}"))
        if tool.forges:
            lay.addWidget(muted("Forges supportées : " + ", ".join(tool.forges)))
        if tool.kind == "provider":
            lay.addWidget(section_title("Services par rôle"))
            for role, sid in tool.services.items():
                svc = self.catalog.get(sid)
                lay.addWidget(muted(f"{role} → {svc.name if svc else sid}"))
            sec = {"yes": "Qualifié", "no": "Non qualifié (régions publiques)", "partial": "Certaines offres",
                   "unknown": "À vérifier"}.get(tool.secnumcloud or "unknown")
            lay.addWidget(muted(f"SecNumCloud : {sec}"))
            if tool.terraform_provider:
                lay.addWidget(muted(f"Provider Terraform : {tool.terraform_provider}"))

        links = []
        if tool.homepage:
            links.append(f'<a href="{tool.homepage}">Site</a>')
        if tool.landscape and tool.landscape.repo_url:
            links.append(f'<a href="{tool.landscape.repo_url}">Dépôt</a>')
        if links:
            ll = QLabel(" · ".join(links))
            ll.setOpenExternalLinks(True)
            lay.addWidget(ll)
        if tool.verified:
            lay.addWidget(muted(f"Fiche vérifiée le {tool.verified}"))

        if brick is not None:
            lay.addWidget(section_title("Paramètres de la brique"))
            lay.addWidget(muted("Valeurs YAML ; elles remplacent les valeurs par défaut de la fiche."))
            self.table = QTableWidget(0, 2)
            self.table.setHorizontalHeaderLabels(["Clé", "Valeur"])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.table.verticalHeader().setVisible(False)
            self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.table.setAccessibleName("Paramètres de la brique")
            params: dict[str, Any] = dict(tool.params)
            params.update(brick.params)
            self._loading = True
            for k, v in params.items():
                self._append_row(k, v, overridden=k in brick.params)
            self._loading = False
            self.table.setFixedHeight(min(280, 44 + 34 * max(1, self.table.rowCount())))
            self.table.itemChanged.connect(self._emit_params)
            lay.addWidget(self.table)
            row = QHBoxLayout()
            add = QPushButton(icon("mdi6.plus"), "Paramètre")
            add.clicked.connect(lambda: self._append_row("cle", "", True, edit=True))
            rm = QPushButton(icon("mdi6.minus"), "Retirer")
            rm.clicked.connect(self._remove_row)
            row.addWidget(add)
            row.addWidget(rm)
            row.addStretch(1)
            lay.addLayout(row)
            delete = QPushButton(icon("mdi6.delete", pal.blocking), "Retirer la brique du pipeline")
            delete.setProperty("class", "danger")
            delete.clicked.connect(lambda: self.removeRequested.emit(brick.uid))
            lay.addWidget(delete)
        else:
            add = QPushButton(icon("mdi6.plus", pal.primary), f"Ajouter à l'étape {STAGE_LABELS[tool.stage]}")
            add.clicked.connect(lambda: self.addRequested.emit(tool.id))
            lay.addWidget(add)
        lay.addStretch(1)
        self.setWidget(w)

    # ------------------------------------------------------------- paramètres
    def _append_row(self, key: str, value: Any, overridden: bool, edit: bool = False) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        text = value if isinstance(value, str) else yaml.safe_dump(value, default_flow_style=True).strip()
        k = QTableWidgetItem(str(key))
        v = QTableWidgetItem(text)
        if not overridden:
            f = k.font()
            f.setItalic(True)
            k.setFont(f)
            k.setToolTip("Valeur par défaut de la fiche")
        self.table.setItem(r, 0, k)
        self.table.setItem(r, 1, v)
        if edit:
            self.table.editItem(k)

    def _remove_row(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self._emit_params()

    def _emit_params(self, *_: object) -> None:
        if self._loading or self._uid is None or self._tool_id is None:
            return
        tool = self.catalog[self._tool_id]
        params: dict[str, Any] = {}
        for r in range(self.table.rowCount()):
            k = self.table.item(r, 0)
            v = self.table.item(r, 1)
            if not k or not k.text().strip():
                continue
            raw = v.text() if v else ""
            try:
                value = yaml.safe_load(raw) if raw else ""
            except yaml.YAMLError:
                value = raw
            if tool.params.get(k.text()) == value:
                continue  # identique au défaut : inutile de le stocker
            params[k.text().strip()] = value
        self.paramsChanged.emit(self._uid, params)
