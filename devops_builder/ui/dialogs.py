"""Boîtes de dialogue : paramètres du projet, génération, à propos."""

from __future__ import annotations

import re
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
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..generators import GenerationResult
from ..model import ENV_ID_PATTERN, ENV_PRESETS, ENVIRONMENTS, LANGUAGES, TARGETS, Environment, Project, env_preset
from .widgets import icon, muted


class EnvironmentsEditor(QWidget):
    """Liste ordonnée des environnements (ordre de promotion) et réglages de chacun."""

    def __init__(self, project: Project, cluster_tools: list[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.envs: list[Environment] = [e.model_copy(deep=True) for e in project.environments]
        self.cluster_tools = cluster_tools
        self._loading = False
        lay = QVBoxLayout(self)
        lay.addWidget(muted("L'ordre de la liste est l'ordre de promotion : la même image est déployée "
                            "d'un environnement au suivant."))
        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setAccessibleName("Environnements, dans l'ordre de promotion")
        row.addWidget(self.list, 1)
        side = QVBoxLayout()
        self.b_add = QPushButton(icon("mdi6.plus"), "Ajouter")
        self.b_del = QPushButton(icon("mdi6.minus"), "Retirer")
        self.b_up = QPushButton(icon("mdi6.arrow-up"), "Monter")
        self.b_down = QPushButton(icon("mdi6.arrow-down"), "Descendre")
        self.preset = QComboBox()
        self.preset.setAccessibleName("Appliquer un modèle d'environnements")
        self.preset.addItem("Modèle…", "")
        for k, v in ENV_PRESETS.items():
            self.preset.addItem(v, k)
        for b in (self.b_add, self.b_del, self.b_up, self.b_down):
            side.addWidget(b)
        side.addWidget(self.preset)
        side.addStretch(1)
        row.addLayout(side)
        lay.addLayout(row)

        form = QFormLayout()
        self.f_id = QLineEdit()
        self.f_label = QLineEdit()
        self.f_label.setPlaceholderText("libellé affiché (facultatif)")
        self.f_kind = QComboBox()
        for k, v in ENVIRONMENTS.items():
            self.f_kind.addItem(v, k)
        self.f_approval = QCheckBox("Exiger une approbation avant de déployer")
        self.f_cluster = QComboBox()
        self.f_cluster.addItem("(automatique)", None)
        for tid, name in cluster_tools:
            self.f_cluster.addItem(name, tid)
        self.f_cluster.setEnabled(len(cluster_tools) > 1)
        self.f_error = QLabel()
        self.f_error.setStyleSheet("color: #d32f2f;")
        form.addRow("Identifiant", self.f_id)
        form.addRow("Libellé", self.f_label)
        form.addRow("Type", self.f_kind)
        form.addRow("Cluster", self.f_cluster)
        form.addRow("", self.f_approval)
        form.addRow("", self.f_error)
        lay.addLayout(form)

        self.list.currentRowChanged.connect(self._show)
        for w in (self.f_id, self.f_label):
            w.textEdited.connect(self._store)
        for w in (self.f_kind, self.f_cluster):
            w.currentIndexChanged.connect(self._store)
        self.f_approval.toggled.connect(self._store)
        self.b_add.clicked.connect(self._add)
        self.b_del.clicked.connect(self._remove)
        self.b_up.clicked.connect(lambda: self._move(-1))
        self.b_down.clicked.connect(lambda: self._move(1))
        self.preset.activated.connect(self._apply_preset)
        self._refresh(0)

    def _refresh(self, row: int) -> None:
        self._loading = True
        self.list.clear()
        for e in self.envs:
            self.list.addItem(f"{e.display}  ({e.id})" + ("  · approbation" if e.approval else ""))
        self._loading = False
        if self.envs:
            self.list.setCurrentRow(max(0, min(row, len(self.envs) - 1)))
        self.b_del.setEnabled(len(self.envs) > 1)

    def _show(self, row: int) -> None:
        if self._loading or not (0 <= row < len(self.envs)):
            return
        e = self.envs[row]
        self._loading = True
        self.f_id.setText(e.id)
        self.f_label.setText(e.label)
        self.f_kind.setCurrentIndex(list(ENVIRONMENTS).index(e.kind))
        self.f_cluster.setCurrentIndex(max(0, self.f_cluster.findData(e.cluster)))
        self.f_approval.setChecked(e.approval)
        self._loading = False
        self._check()

    def _store(self, *_: object) -> None:
        row = self.list.currentRow()
        if self._loading or not (0 <= row < len(self.envs)):
            return
        e = self.envs[row]
        e.id = self.f_id.text().strip()
        e.label = self.f_label.text().strip()
        e.kind = self.f_kind.currentData()
        e.cluster = self.f_cluster.currentData()
        e.approval = self.f_approval.isChecked()
        item = self.list.item(row)
        item.setText(f"{e.display}  ({e.id})" + ("  · approbation" if e.approval else ""))
        self._check()

    def _check(self) -> bool:
        ids = [e.id for e in self.envs]
        bad = [i for i in ids if not re.fullmatch(ENV_ID_PATTERN, i)]
        msg = ""
        if bad:
            msg = f"Identifiant invalide : {bad[0] or '(vide)'} (minuscules, chiffres et tirets, commence par une lettre)."
        elif len(set(ids)) != len(ids):
            msg = "Deux environnements ont le même identifiant."
        self.f_error.setText(msg)
        return not msg

    def _add(self) -> None:
        n = 1
        while f"env{n}" in {e.id for e in self.envs}:
            n += 1
        self.envs.append(Environment(id=f"env{n}", kind="staging"))
        self._refresh(len(self.envs) - 1)

    def _remove(self) -> None:
        row = self.list.currentRow()
        if len(self.envs) > 1 and 0 <= row < len(self.envs):
            del self.envs[row]
            self._refresh(row)

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        dest = row + delta
        if 0 <= row < len(self.envs) and 0 <= dest < len(self.envs):
            self.envs[row], self.envs[dest] = self.envs[dest], self.envs[row]
            self._refresh(dest)

    def _apply_preset(self, index: int) -> None:
        key = self.preset.itemData(index)
        if key:
            old = {e.id: e for e in self.envs}
            self.envs = []
            for e in env_preset(key):  # conserve surcharges et cluster des environnements déjà présents
                if e.id in old:
                    e.overrides, e.cluster = old[e.id].overrides, old[e.id].cluster
                self.envs.append(e)
            self._refresh(0)
        self.preset.setCurrentIndex(0)


class ProjectSettingsDialog(QDialog):
    def __init__(self, project: Project, parent: QWidget | None = None, catalog=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres du projet")
        self.setMinimumWidth(600)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.name = QLineEdit(project.name)
        self.description = QLineEdit(project.description)
        self.target = QComboBox()
        for k, v in TARGETS.items():
            self.target.addItem(v, k)
        self.target.setCurrentIndex(list(TARGETS).index(project.target))
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
        form.addRow("Cible d'hébergement (production)", self.target)
        form.addRow("Langage de l'application", self.language)
        form.addRow("Nom de l'image", self.image)
        form.addRow("Port de l'application", self.port)
        form.addRow("Authentification cloud en CI", self.auth)
        form.addRow("Politique de licence", self.license)
        form.addRow("", self.secnum)
        general = QWidget()
        general.setLayout(form)

        clusters = []
        for _, b in project.all_bricks():
            t = catalog.get(b.tool) if catalog else None
            if t and "kubernetes-cluster" in t.roles and (b.tool, t.name) not in clusters:
                clusters.append((b.tool, t.name))
        self.envs_editor = EnvironmentsEditor(project, clusters)
        self.tabs = QTabWidget()
        self.tabs.addTab(general, "Général")
        self.tabs.addTab(self.envs_editor, "Environnements")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Appliquer")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addWidget(buttons)

    def _accept(self) -> None:
        if not self.envs_editor._check():
            self.tabs.setCurrentWidget(self.envs_editor)
            return
        self.accept()

    def apply_to(self, project: Project) -> None:
        project.name = self.name.text().strip() or "Projet"
        project.description = self.description.text().strip()
        project.target = self.target.currentData()
        project.environments = [e.model_copy(deep=True) for e in self.envs_editor.envs]
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
        check = QPushButton(icon("mdi6.check-decagram-outline"), "Valider…")
        check.setToolTip("Contrôler les fichiers avec les linters installés, puis tester dans kind")
        to_git = QPushButton(icon("mdi6.source-branch-plus"), "Exporter vers Git…")
        to_git.setProperty("class", "success")
        to_git.setToolTip("Nouvelle branche, commit, push et demande de fusion")
        to_dir = QPushButton(icon("mdi6.folder-download"), "Écrire dans un dossier…")
        to_zip = QPushButton(icon("mdi6.folder-zip"), "Archive .zip…")
        close = QPushButton("Fermer")
        check.clicked.connect(self._validate)
        to_git.clicked.connect(self._export_git)
        to_dir.clicked.connect(self._export_dir)
        to_zip.clicked.connect(self._export_zip)
        close.clicked.connect(self.accept)
        for b in (check, to_git, to_dir, to_zip):
            row.addWidget(b)
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

    def _validate(self) -> None:
        from .validation import ValidationDialog
        ValidationDialog(self.result, self).exec()

    def _export_git(self) -> None:
        from .export import GitExportDialog
        GitExportDialog(self.result, self).exec()

    def _export_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier de destination")
        if d:
            self.export_to(Path(d))

    def export_to(self, target: Path) -> None:
        """Écrit directement dans un dossier vide ; sinon montre d'abord les différences."""
        from .. import sync
        from .export import SyncDialog
        changes = sync.plan(self.result.files, target)
        if all(c.status == sync.NEW for c in changes):
            written = sync.apply(changes, target)
            QMessageBox.information(self, "Export terminé", f"{len(written) - 1} fichiers écrits dans {target}.")
            return
        dlg = SyncDialog(self.result, target, self)
        if dlg.exec() and dlg.written:
            n = len([w for w in dlg.written if w != sync.MANIFEST])
            QMessageBox.information(self, "Export terminé", f"{n} fichier(s) écrit(s) ou supprimé(s) dans {target}.")

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
