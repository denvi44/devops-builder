"""L'application mise en pipeline : son dossier, ce que l'analyse y a trouvé, ses réglages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from ..model import LANGUAGES, Project
from .widgets import icon, muted, section_title

LANGUAGE_ICONS = {"python": "mdi6.language-python", "node": "mdi6.nodejs", "java": "mdi6.language-java",
                  "go": "mdi6.language-go", "dotnet": "mdi6.dot-net", "other": "mdi6.application-outline"}


def app_label(project: Project) -> str:
    app = project.app
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
        self.resize(760, 620)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Désigner le dossier de l'application : DevOps Builder y lit le langage, le port, le "
                            "Dockerfile, la CI et la forge déjà en place, et propose les briques qui vont avec."))
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

    def analyse(self) -> None:
        path = self.folder.path()
        self.found.clear()
        self.bricks.clear()
        if not path:
            self.status.setText("Choisir d'abord le dossier de l'application.")
            return
        try:
            self.profile = appscan.scan(path)
        except ValueError as exc:
            self.profile = None
            self.status.setText(str(exc))
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
        for tool_id in self.chosen_bricks():
            if not project.bricks_for(tool_id):
                project.add(tool_id, self.catalog[tool_id].stage)

