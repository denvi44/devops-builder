# SPDX-License-Identifier: Apache-2.0
"""L'application mise en pipeline : son dossier, ce que l'analyse y a trouvé, ses réglages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import appscan
from ..catalog import Catalog
from ..messages import explain
from ..model import LANGUAGES, Component, Project
from .widgets import icon, muted, section_title

LANGUAGE_ICONS = {"python": "mdi6.language-python", "node": "mdi6.nodejs", "java": "mdi6.language-java",
                  "go": "mdi6.language-go", "dotnet": "mdi6.dot-net", "other": "mdi6.application-outline"}


def app_label(project: Project) -> str:
    app = project.app
    if not app.enabled:
        return "Plateforme seule · sans application"
    return f"{app.image_name} · {LANGUAGES.get(app.language, app.language)} · port {app.port}"


class FolderPicker(QWidget):
    """Champ « dossier de l'application » avec boutons Choisir et Analyser."""

    def __init__(self, path: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(path)
        self.edit.setPlaceholderText("dossier du code (dépôt Git cloné)")
        self.edit.setAccessibleName("Dossier de l'application")
        self.browse = QPushButton(icon("mdi6.folder-open-outline"), "Choisir…")
        self.scan = QPushButton(icon("mdi6.magnify-scan"), "Analyser")
        self.scan.setProperty("class", "success")
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.browse)
        lay.addWidget(self.scan)
        self.browse.clicked.connect(self._browse)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier de l'application", self.edit.text() or str(Path.home()))
        if d:
            self.edit.setText(d)
            self.scan.click()

    def path(self) -> str:
        return self.edit.text().strip()


class ApplicationDialog(QDialog):
    """Réglages de l'application ; l'analyse de son dossier propose réglages et briques."""

    def __init__(self, project: Project, catalog: Catalog, parent: QWidget | None = None):
        super().__init__(parent)
        self.project, self.catalog = project, catalog
        self.profile: appscan.AppProfile | None = None
        self.setWindowTitle("Application")
        self.resize(760, 760)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Désigner le dossier de l'application : DevOps Builder y lit le langage, le port, le "
                            "Dockerfile, les bases de données, la CI et la forge déjà en place, et propose les "
                            "briques qui vont avec."))
        form = QFormLayout()
        self.folder = FolderPicker(project.app.source)
        self.folder.scan.clicked.connect(self.analyse)
        form.addRow("Dossier", self.folder)
        self.image = QLineEdit(project.app.image_name)
        self.image.setAccessibleName("Nom de l'image")
        self.language = QComboBox()
        for k, v in LANGUAGES.items():
            self.language.addItem(icon(LANGUAGE_ICONS.get(k, "mdi6.application-outline")), v, k)
        self.language.setCurrentIndex(max(0, self.language.findData(project.app.language)))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(project.app.port)
        form.addRow("Nom de l'image", self.image)
        form.addRow("Langage", self.language)
        form.addRow("Port d'écoute", self.port)
        lay.addLayout(form)
        self._build_components(lay, project)
        lay.addWidget(section_title("Ce que l'analyse a trouvé"))
        self.found = QListWidget()
        self.found.setAccessibleName("Détections")
        self.found.setMaximumHeight(170)
        lay.addWidget(self.found)
        lay.addWidget(section_title("Briques proposées"))
        self.bricks = QListWidget()
        self.bricks.setAccessibleName("Briques proposées par l'analyse")
        lay.addWidget(self.bricks, 1)
        self.status = muted("Pas encore analysé." if not project.app.source else "Cliquer « Analyser » pour relire le dossier.")
        lay.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Appliquer")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # ------------------------------------------------------ applications supplémentaires
    def _build_components(self, lay: QVBoxLayout, project: Project) -> None:
        lay.addWidget(section_title("Applications supplémentaires"))
        lay.addWidget(muted("API, interface, worker… : chaque composant a son Dockerfile dans son dossier du dépôt, "
                            "son image, ses tests et son déploiement, dans le même pipeline."))
        self._comps: list[Component] = [c.model_copy() for c in project.components]
        self._comp_row = -1
        self.comp_list = QListWidget()
        self.comp_list.setAccessibleName("Applications supplémentaires")
        self.comp_list.setMaximumHeight(90)
        for c in self._comps:
            self.comp_list.addItem(self._comp_text(c))
        box = QHBoxLayout()
        self.comp_add = QPushButton(icon("mdi6.plus"), "Ajouter")
        self.comp_remove = QPushButton(icon("mdi6.delete-outline"), "Retirer")
        box.addWidget(self.comp_add)
        box.addWidget(self.comp_remove)
        box.addStretch(1)
        form = QFormLayout()
        self.comp_id = QLineEdit()
        self.comp_id.setAccessibleName("Identifiant du composant")
        self.comp_id.setPlaceholderText("api, front, worker…")
        self.comp_lang = QComboBox()
        self.comp_lang.setAccessibleName("Langage du composant")
        for k, v in LANGUAGES.items():
            self.comp_lang.addItem(icon(LANGUAGE_ICONS.get(k, "mdi6.application-outline")), v, k)
        self.comp_port = QSpinBox()
        self.comp_port.setRange(1, 65535)
        self.comp_port.setAccessibleName("Port du composant")
        self.comp_dir = QLineEdit()
        self.comp_dir.setAccessibleName("Dossier du composant")
        self.comp_dir.setPlaceholderText("services/<identifiant>")
        self.comp_public = QCheckBox("Exposé à l'extérieur (chemin /<identifiant> derrière Traefik)")
        form.addRow("Identifiant", self.comp_id)
        form.addRow("Langage", self.comp_lang)
        form.addRow("Port d'écoute", self.comp_port)
        form.addRow("Dossier du dépôt", self.comp_dir)
        form.addRow("", self.comp_public)
        lay.addWidget(self.comp_list)
        lay.addLayout(box)
        lay.addLayout(form)
        self.comp_add.clicked.connect(self._comp_add)
        self.comp_remove.clicked.connect(self._comp_remove)
        self.comp_list.currentRowChanged.connect(self._comp_select)
        self._comp_enable(False)
        if self._comps:
            self.comp_list.setCurrentRow(0)

    @staticmethod
    def _comp_text(c: Component) -> str:
        return f"{c.id or '(sans nom)'} · {LANGUAGES.get(c.language, c.language)} · port {c.port}" + \
            (" · exposé" if c.public else "")

    def _comp_enable(self, on: bool) -> None:
        for w in (self.comp_id, self.comp_lang, self.comp_port, self.comp_dir, self.comp_public, self.comp_remove):
            w.setEnabled(on)

    def _comp_commit(self) -> None:
        row = self._comp_row
        if not 0 <= row < len(self._comps):
            return
        c = self._comps[row]
        c.id = appscan.slug(self.comp_id.text()) if self.comp_id.text().strip() else ""
        c.language = self.comp_lang.currentData()
        c.port = self.comp_port.value()
        c.source = self.comp_dir.text().strip()
        c.public = self.comp_public.isChecked()
        self.comp_list.item(row).setText(self._comp_text(c))

    def _comp_select(self, row: int) -> None:
        self._comp_commit()
        self._comp_row = row
        self._comp_enable(0 <= row < len(self._comps))
        if not 0 <= row < len(self._comps):
            return
        c = self._comps[row]
        self.comp_id.setText(c.id)
        self.comp_lang.setCurrentIndex(max(0, self.comp_lang.findData(c.language)))
        self.comp_port.setValue(c.port)
        self.comp_dir.setText(c.source)
        self.comp_public.setChecked(c.public)

    def _comp_add(self) -> None:
        self._comp_commit()
        taken = {c.id for c in self._comps}
        n = 1
        while f"service-{n}" in taken:
            n += 1
        self._comps.append(Component(id=f"service-{n}", port=8080 + len(self._comps)))
        self.comp_list.addItem(self._comp_text(self._comps[-1]))
        self.comp_list.setCurrentRow(len(self._comps) - 1)

    def _comp_remove(self) -> None:
        row = self.comp_list.currentRow()
        if not 0 <= row < len(self._comps):
            return
        self._comp_row = -1
        del self._comps[row]
        self.comp_list.takeItem(row)
        self._comp_select(self.comp_list.currentRow())

    def analyse(self) -> None:
        path = self.folder.path()
        self.found.clear()
        self.bricks.clear()
        if not path:
            self.status.setText("Choisir d'abord le dossier de l'application.")
            return
        try:
            self.profile = appscan.scan(path)
        except (ValueError, OSError) as exc:  # dossier refusé, ou illisible (droits)
            self.profile = None
            self.status.setText(str(exc) if isinstance(exc, ValueError) else explain(exc, path))
            return
        p = self.profile
        for line in p.summary():
            QListWidgetItem(icon("mdi6.check", None), line, self.found)
        self.image.setText(p.image_name)
        self.language.setCurrentIndex(max(0, self.language.findData(p.language)))
        if p.port:
            self.port.setValue(p.port)
        proposals = appscan.proposed_bricks(p, self.project, self.catalog)
        for tool_id, why in proposals:
            tool = self.catalog[tool_id]
            item = QListWidgetItem(f"{tool.name} — {why}", self.bricks)
            item.setData(Qt.ItemDataRole.UserRole, tool_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
        self.status.setText(f"{len(p.summary())} élément(s) détecté(s) · {len(proposals)} brique(s) proposée(s)"
                            + ("" if proposals else " : le pipeline couvre déjà ce que l'application demande."))

    def chosen_bricks(self) -> list[str]:
        return [self.bricks.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.bricks.count())
                if self.bricks.item(i).checkState() == Qt.CheckState.Checked]

    def apply_to(self, project: Project) -> None:
        project.app.source = self.folder.path()
        project.app.image_name = appscan.slug(self.image.text()) if self.image.text().strip() else project.app.image_name
        project.app.language = self.language.currentData()
        project.app.port = self.port.value()
        self._comp_commit()
        project.components = [c.model_copy() for c in self._comps if c.id]
        for tool_id in self.chosen_bricks():
            if not project.bricks_for(tool_id):
                params = appscan.proposed_params(self.profile, tool_id, project, self.catalog) if self.profile else {}
                project.add(tool_id, self.catalog[tool_id].stage, **params)

