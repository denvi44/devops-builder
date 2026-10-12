"""Panneau des propriétés : fiche de l'outil et paramètres de la brique."""

from __future__ import annotations

from typing import Any

import yaml
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from ..model import STAGE_LABELS, BrickInstance, Project, Tool
from . import theme
from .widgets import FlowRow, chip, icon, muted, plain, section_title

HOSTING = {"kubernetes": "Kubernetes", "docker-host": "Hôte Docker", "vm": "VM", "saas": "SaaS",
           "ci": "Job CI", "cli": "CLI"}
LIFECYCLE = {"active": "Actif", "maintenance-ended": "Maintenance arrêtée", "archived": "Archivé",
             "discontinued": "Arrêté"}


class PropertiesPanel(QScrollArea):
    paramsChanged = Signal(str, dict)   # uid, params
    overridesChanged = Signal(str, str, dict)  # env_id, tool_id, params
    removeRequested = Signal(str)
    addRequested = Signal(str)          # tool_id (fiche affichée depuis la palette)
    ficheRequested = Signal(str)        # créer une fiche depuis le Landscape ou modifier une fiche personnelle

    def __init__(self, catalog: Catalog, parent: QWidget | None = None):
        super().__init__(parent)
        self.catalog = catalog
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self._uid: str | None = None
        self._tool_id: str | None = None
        self._loading = False
        self._env_id: str | None = None  # environnement choisi pour éditer les surcharges
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

    def show_tool(self, tool: Tool, brick: BrickInstance | None = None, project: Project | None = None) -> None:
        if brick is None or brick.uid != self._uid:
            self._env_id = None if (project is None or not self._env_id or not project.env(self._env_id)) else self._env_id
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
        if tool.origin == "utilisateur":
            chips.append(chip("Fiche personnelle", tooltip="Catalogue personnel"))
        if tool.corrections:
            chips.append(chip("Corrigée", tooltip="Valeurs d'origine : " + ", ".join(
                f"{k} = {v}" for k, v in tool.corrections.items())))
        if tool.dev_only:
            chips.append(chip("Développement uniquement"))
        lay.addWidget(FlowRow(chips, per_row=3))

        if tool.lifecycle_note:
            note = QLabel(f"⚠ {tool.lifecycle_note}")
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {pal.warning};")
            lay.addWidget(note)

        if brick is not None:
            self._brick_section(lay, tool, brick, project)

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
        if tool.repo_url:
            links.append(f'<a href="{tool.repo_url}">Dépôt</a>')
        if links:
            ll = QLabel(" · ".join(links))
            ll.setOpenExternalLinks(True)
            lay.addWidget(ll)
        if tool.verified:
            lay.addWidget(muted(f"Fiche vérifiée le {tool.verified}"))

        if brick is None:
            add = QPushButton(icon("mdi6.plus", pal.primary), plain(f"Ajouter à l'étape {STAGE_LABELS[tool.stage]}"))
            add.clicked.connect(lambda: self.addRequested.emit(tool.id))
            lay.addWidget(add)
        if not tool.curated or tool.origin == "utilisateur":
            label = "Créer une fiche vérifiée…" if not tool.curated else "Modifier la fiche…"
            edit = QPushButton(icon("mdi6.file-edit-outline", pal.text), label)
            edit.setToolTip("Fiche du catalogue personnel : contrôlée par les règles comme une fiche livrée")
            edit.clicked.connect(lambda: self.ficheRequested.emit(tool.id))
            lay.addWidget(edit)
        lay.addStretch(1)
        self.setWidget(w)

    def _ports_section(self, lay: QVBoxLayout, tool: Tool, project: Project) -> None:
        from ..ports import port_plan
        mine = [e for e in port_plan(project, self.catalog) if e.component_id == tool.id]
        if not mine:
            return
        lay.addWidget(section_title("Ports"))
        for e in mine:
            where = f"{e.env} : " if project.multi_env else ""
            port = f"{e.host_port} → {e.container_port}" if e.host_port is not None else f"{e.container_port}"
            label = muted(f"{where}{port}" + (f" ({e.usage})" if e.usage else "") + (f" ⚠ {e.conflict}" if e.conflict else ""))
            if e.conflict:
                label.setStyleSheet(f"color: {theme.current().blocking};")
            label.setToolTip(e.exposure)
            lay.addWidget(label)

    def _connection_section(self, lay: QVBoxLayout, tool: Tool, project: Project) -> None:
        from ..datainfo import infos
        info = infos(project, self.catalog).get(tool.id)
        if info is None:
            return
        lay.addWidget(section_title("Connexion"))
        for text in (f"{info.badge} — {info.where}.", f"L'application lit {info.connection}.",
                     f"Mot de passe / URL : {info.secret}.", f"Sauvegarde : {info.backup}."):
            label = muted(text)
            label.setWordWrap(True)
            lay.addWidget(label)

    # ------------------------------------------------------------- brique posée
    def _brick_section(self, lay: QVBoxLayout, tool: Tool, brick: BrickInstance, project: Project | None) -> None:
        pal = theme.current()
        if tool.param_schema:
            from .param_form import ParamForm
            lay.addWidget(section_title("Paramètres de la brique"))
            env = None
            if project is not None and project.multi_env:
                self.env_combo = QComboBox()
                self.env_combo.setAccessibleName("Environnement des paramètres")
                self.env_combo.addItem("Tous les environnements", "")
                for e in project.environments:
                    count = len(e.overrides.get(tool.id, {}))
                    self.env_combo.addItem(e.display + (f" ({count} surcharge{'s' if count > 1 else ''})" if count else ""), e.id)
                if self._env_id and project.env(self._env_id):
                    self.env_combo.setCurrentIndex(self.env_combo.findData(self._env_id))
                    env = project.env(self._env_id)
                self.env_combo.currentIndexChanged.connect(
                    lambda _i: self._switch_env(tool, brick, project, self.env_combo.currentData()))
                lay.addWidget(self.env_combo)
                lay.addWidget(muted("Choisir un environnement pour y surcharger une valeur ; vide = valeur commune."
                                    if env is None else
                                    f"Surcharges de « {env.display} » ; laisser vide pour hériter de la valeur commune."))
            self.form = ParamForm(tool, brick, project, env)
            if env is None:
                self.form.changed.connect(lambda params, uid=brick.uid: self.paramsChanged.emit(uid, params))
            else:
                self.form.changed.connect(
                    lambda params, eid=env.id, tid=tool.id: self.overridesChanged.emit(eid, tid, params))
            lay.addWidget(self.form)
        else:
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
        if project is not None:
            self._ports_section(lay, tool, project)
            self._connection_section(lay, tool, project)
        delete = QPushButton(icon("mdi6.delete", pal.blocking), "Retirer la brique du pipeline")
        delete.setProperty("class", "danger")
        delete.clicked.connect(lambda: self.removeRequested.emit(brick.uid))
        lay.addWidget(delete)
        if project is not None:
            from ..suggest import suggestions
            sugg = suggestions(project, self.catalog, tool.id)
            if sugg:
                lay.addWidget(section_title("Souvent associé"))
                for t in sugg:
                    b = QPushButton(icon("mdi6.plus", pal.primary), plain(t.name))
                    b.setToolTip(f"Ajouter {t.name} à l'étape {STAGE_LABELS[t.stage]}")
                    b.setAccessibleName(f"Ajouter {t.name}")
                    b.clicked.connect(lambda checked=False, tid=t.id: self.addRequested.emit(tid))
                    lay.addWidget(b)

    def _switch_env(self, tool: Tool, brick: BrickInstance, project: Project, env_id: str) -> None:
        self._env_id = env_id or None
        # Reconstruit le panneau après le signal : la liste qui l'émet appartient au panneau remplacé.
        QTimer.singleShot(0, lambda: self.show_tool(tool, brick, project))

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
