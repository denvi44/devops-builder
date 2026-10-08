"""Boîtes de dialogue : paramètres du projet, génération, à propos."""

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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..generators import GenerationResult
from ..model import ENVIRONMENTS, LANGUAGES, TARGETS, Project
from .widgets import icon, muted


class ProjectSettingsDialog(QDialog):
    def __init__(self, project: Project, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres du projet")
        self.setMinimumWidth(520)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.name = QLineEdit(project.name)
        self.description = QLineEdit(project.description)
        self.target = QComboBox()
        for k, v in TARGETS.items():
            self.target.addItem(v, k)
        self.target.setCurrentIndex(list(TARGETS).index(project.target))
        self.environment = QComboBox()
        for k, v in ENVIRONMENTS.items():
            self.environment.addItem(v, k)
        self.environment.setCurrentIndex(list(ENVIRONMENTS).index(project.environment))
        self.language = QComboBox()
        for k, v in LANGUAGES.items():
            self.language.addItem(v, k)
        self.language.setCurrentIndex(list(LANGUAGES).index(project.app.language))
        self.image = QLineEdit(project.app.image_name)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(project.app.port)
        self.secnum = QCheckBox("Exiger un hébergement qualifié SecNumCloud")
        self.secnum.setChecked(project.secnumcloud)
        self.auth = QComboBox()
        self.auth.addItem("Fédération d'identité OIDC (recommandé)", "oidc")
        self.auth.addItem("Clés d'accès statiques", "static")
        self.auth.setCurrentIndex(0 if project.cloud_auth == "oidc" else 1)
        self.license = QComboBox()
        self.license.addItem("Toutes licences (signaler les non-OSS)", "any")
        self.license.addItem("Open source uniquement", "oss-only")
        self.license.setCurrentIndex(0 if project.license_policy == "any" else 1)

        form.addRow("Nom", self.name)
        form.addRow("Description", self.description)
        form.addRow("Cible d'hébergement", self.target)
        form.addRow("Environnement", self.environment)
        form.addRow("Langage de l'application", self.language)
        form.addRow("Nom de l'image", self.image)
        form.addRow("Port de l'application", self.port)
        form.addRow("Authentification cloud en CI", self.auth)
        form.addRow("Politique de licence", self.license)
        form.addRow("", self.secnum)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Appliquer")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def apply_to(self, project: Project) -> None:
        project.name = self.name.text().strip() or "Projet"
        project.description = self.description.text().strip()
        project.target = self.target.currentData()
        project.environment = self.environment.currentData()
        project.app.language = self.language.currentData()
        project.app.image_name = self.image.text().strip() or "mon-app"
        project.app.port = self.port.value()
        project.secnumcloud = self.secnum.isChecked()
        project.cloud_auth = self.auth.currentData()
        project.license_policy = self.license.currentData()


class GenerateDialog(QDialog):
    """Aperçu des fichiers générés, puis export en dossier ou en archive."""

    def __init__(self, result: GenerationResult, parent: QWidget | None = None):
        super().__init__(parent)
        self.result = result
        self.setWindowTitle("Fichiers générés")
        self.resize(1000, 640)
        lay = QVBoxLayout(self)
        warn = [d for d in result.diagnostics if d.severity.value == "avertissement"]
        head = f"{len(result.files)} fichiers générés"
        if warn:
            head += f" · {len(warn)} avertissement(s) restant(s), détaillés dans PIPELINE.md"
        lay.addWidget(muted(head))

        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName("Fichiers générés")
        self._fill_tree()
        split.addWidget(self.tree)
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("codePreview")
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.preview.setAccessibleName("Aperçu du fichier")
        split.addWidget(self.preview)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        lay.addWidget(split, 1)

        row = QHBoxLayout()
        to_dir = QPushButton(icon("mdi6.folder-download"), "Exporter vers un dossier…")
        to_dir.setProperty("class", "success")
        to_zip = QPushButton(icon("mdi6.folder-zip"), "Exporter en archive .zip…")
        close = QPushButton("Fermer")
        to_dir.clicked.connect(self._export_dir)
        to_zip.clicked.connect(self._export_zip)
        close.clicked.connect(self.accept)
        row.addWidget(to_dir)
        row.addWidget(to_zip)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)

        self.tree.currentItemChanged.connect(self._show)
        first = self._find_item("PIPELINE.md")
        if first:
            self.tree.setCurrentItem(first)

    def _fill_tree(self) -> None:
        nodes: dict[str, QTreeWidgetItem] = {}
        for rel in sorted(self.result.files):
            parts = rel.split("/")
            parent: QTreeWidgetItem | None = None
            path = ""
            for i, part in enumerate(parts):
                path = f"{path}/{part}" if path else part
                if path in nodes:
                    parent = nodes[path]
                    continue
                item = QTreeWidgetItem([part])
                is_file = i == len(parts) - 1
                item.setIcon(0, icon("mdi6.file-document-outline" if is_file else "mdi6.folder-outline"))
                if is_file:
                    item.setData(0, Qt.ItemDataRole.UserRole, rel)
                if parent is None:
                    self.tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                nodes[path] = item
                parent = item
        self.tree.expandAll()

    def _find_item(self, rel: str) -> QTreeWidgetItem | None:
        it = self.tree.findItems(rel.split("/")[-1], Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
        return it[0] if it else None

    def _show(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        rel = item.data(0, Qt.ItemDataRole.UserRole)
        if rel:
            self.preview.setPlainText(self.result.files[rel])

    def _export_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier de destination")
        if not d:
            return
        target = Path(d)
        clashes = [r for r in self.result.files if (target / r).exists()]
        if clashes:
            ok = QMessageBox.question(self, "Écraser ?",
                                      f"{len(clashes)} fichier(s) existent déjà dans ce dossier. Les remplacer ?")
            if ok != QMessageBox.StandardButton.Yes:
                return
        written = self.result.write(target)
        QMessageBox.information(self, "Export terminé", f"{len(written)} fichiers écrits dans {target}.")

    def _export_zip(self) -> None:
        name = self.result.ir.project.app.image_name or "pipeline"
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer l'archive", f"{name}-pipeline.zip", "Archive zip (*.zip)")
        if not path:
            return
        Path(path).write_bytes(self.result.zip_bytes())
        QMessageBox.information(self, "Export terminé", f"Archive enregistrée : {path}")


def about_text(n_curated: int, n_total: int, n_rules: int) -> str:
    return (
        "<h3>DevOps Builder</h3>"
        "<p>Composer des pipelines DevOps à partir du CNCF Landscape, avec vérification "
        "des incompatibilités avant génération.</p>"
        f"<p>{n_curated} fiches vérifiées · {n_total} outils au catalogue · {n_rules} règles.</p>"
        "<p>Interface Material (PySide6 + qt-material). Les fichiers générés sont à relire "
        "avant usage.</p>"
    )
