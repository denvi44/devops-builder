# SPDX-License-Identifier: Apache-2.0
"""Bouton « Valider » : contrôles locaux des fichiers générés, puis test dans un cluster kind."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import validate
from ..generators import GenerationResult
from ..generators.localtest import KIND_TEST
from . import theme
from .widgets import icon, muted

STATUS_ICONS = {validate.OK: "mdi6.check-circle", validate.FAILED: "mdi6.close-circle",
                validate.MISSING: "mdi6.help-circle-outline", validate.SKIPPED: "mdi6.minus-circle-outline",
                "en attente": "mdi6.clock-outline", "en cours": "mdi6.progress-clock"}


def _status_color(status: str) -> str:
    p = theme.current()
    return {validate.OK: p.ok, validate.FAILED: p.blocking, validate.MISSING: p.warning}.get(status, p.text_muted)


class _ValidationThread(QThread):
    result = Signal(object)

    def __init__(self, files: dict[str, str], network: bool):
        super().__init__()
        self.files, self.network = files, network
        self.stop = False

    def run(self) -> None:
        def on_result(res: validate.CheckResult) -> None:
            self.result.emit(res)
        validate.validate_files(self.files, network=self.network, on_result=on_result,
                                should_stop=lambda: self.stop)


class ValidationDialog(QDialog):
    def __init__(self, result: GenerationResult, parent: QWidget | None = None):
        super().__init__(parent)
        self.result = result
        self.results: dict[str, validate.CheckResult] = {}
        self.worker: _ValidationThread | None = None
        self.setWindowTitle("Valider les fichiers générés")
        self.resize(1000, 620)
        lay = QVBoxLayout(self)
        lay.addWidget(muted(f"{len(result.files)} fichiers contrôlés avec les outils installés sur ce poste. "
                            "Un outil absent n'empêche pas les autres contrôles."))
        self.network = QCheckBox("Inclure les contrôles qui téléchargent des schémas ou des providers")
        self.network.setChecked(True)
        lay.addWidget(self.network)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Contrôle", "État", "Fichiers"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAccessibleName("Contrôles")
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.currentItemChanged.connect(self._show)
        split.addWidget(self.tree)
        self.output = QPlainTextEdit()
        self.output.setObjectName("codePreview")
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setAccessibleName("Sortie du contrôle")
        split.addWidget(self.output)
        split.setSizes([520, 460])
        lay.addWidget(split, 1)
        self.summary = muted("")
        lay.addWidget(self.summary)
        row = QHBoxLayout()
        self.run_btn = QPushButton(icon("mdi6.play-circle-outline"), "Lancer les contrôles")
        self.run_btn.setProperty("class", "success")
        self.run_btn.clicked.connect(self.start)
        self.kind_btn = QPushButton(icon("mdi6.kubernetes"), "Tester dans kind…")
        self.kind_btn.setToolTip("Déployer le chart ou l'overlay dans un cluster kind jetable")
        self.kind_btn.setEnabled(KIND_TEST in result.files)
        if KIND_TEST not in result.files:
            self.kind_btn.setToolTip("Disponible quand le pipeline déploie un chart Helm ou un overlay Kustomize")
        self.kind_btn.clicked.connect(self.open_kind)
        self.close_btn = QPushButton("Fermer")
        self.close_btn.clicked.connect(self.accept)
        row.addWidget(self.run_btn)
        row.addWidget(self.kind_btn)
        row.addStretch(1)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self._fill()

    def _fill(self) -> None:
        self.tree.clear()
        self.items: dict[str, QTreeWidgetItem] = {}
        for check, files in validate.plan_checks(self.result.files):
            available = check.command() is not None
            status = "en attente" if available else validate.MISSING
            item = QTreeWidgetItem([check.label, status, str(len(files))])
            item.setData(0, Qt.ItemDataRole.UserRole, check.id)
            item.setToolTip(2, "\n".join(files))
            self._paint(item, status)
            if not available:
                hint = validate.install_hint(check.hint)
                self.results[check.id] = validate.CheckResult(
                    check.id, check.label, validate.MISSING, files, hint=hint,
                    output=f"Outil introuvable : {' ou '.join(check.tools)}.\nInstallation : {hint}\n\n"
                           "Fichiers générés qui demandent ce contrôle (ils viennent des briques du pipeline) :\n"
                           + "\n".join(f"  {f}" for f in files))
            self.tree.addTopLevelItem(item)
            self.items[check.id] = item
        missing = sum(1 for r in self.results.values() if r.status == validate.MISSING)
        self.summary.setText(f"{len(self.items)} contrôle(s) applicable(s)"
                             + (f", dont {missing} sans outil installé (sélectionner la ligne pour l'installer)." if missing
                                else "."))
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _paint(self, item: QTreeWidgetItem, status: str) -> None:
        item.setText(1, status)
        item.setIcon(1, icon(STATUS_ICONS.get(status, "mdi6.circle-outline"), _status_color(status)))
        item.setForeground(1, theme.qcolor(_status_color(status)))

    def _show(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        res = self.results.get(item.data(0, Qt.ItemDataRole.UserRole))
        if res is None:
            self.output.setPlainText("Pas encore lancé.\n\nFichiers concernés :\n" + item.toolTip(2))
        else:
            self.output.setPlainText(res.output or "Aucune sortie.")

    def start(self) -> None:
        if self.worker is not None:
            return
        self.results.clear()
        for item in self.items.values():
            self._paint(item, "en cours")
        self.worker = _ValidationThread(self.result.files, self.network.isChecked())
        self.worker.result.connect(self._on_result)
        self.worker.finished.connect(self._over)
        self.run_btn.setEnabled(False)
        self.summary.setText("Contrôles en cours…")
        self.worker.start()

    def _on_result(self, res: validate.CheckResult) -> None:
        self.results[res.id] = res
        item = self.items.get(res.id)
        if item is not None:
            self._paint(item, res.status)
            if res.seconds:
                item.setToolTip(1, f"{res.seconds:.1f} s")
            if item is self.tree.currentItem():
                self._show(item)

    def _over(self) -> None:
        self.worker = None
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Relancer les contrôles")
        res = list(self.results.values())
        self.summary.setText(validate.summary(res))
        failed = next((self.items[r.id] for r in res if r.failed and r.id in self.items), None)
        if failed is not None:
            self.tree.setCurrentItem(failed)
        elif self.tree.currentItem() is not None:
            self._show(self.tree.currentItem())

    def open_kind(self) -> None:
        KindTestDialog(self.result, self).exec()

    def reject(self) -> None:
        if self.worker is not None:
            self.worker.stop = True
            self.worker.wait(30000)
        super().reject()

    def accept(self) -> None:
        if self.worker is not None:
            self.worker.stop = True
            self.worker.wait(30000)
        super().accept()


class KindTestDialog(QDialog):
    """Lance scripts/test-kind.sh dans un dossier temporaire et affiche sa sortie en direct."""

    TOOLS = ("docker", "kind", "kubectl", "bash")

    def __init__(self, result: GenerationResult, parent: QWidget | None = None):
        super().__init__(parent)
        self.result = result
        self.proc: QProcess | None = None
        self.exit_code: int | None = None
        self.tmp = tempfile.TemporaryDirectory(prefix="devops-builder-kind-")
        self.setWindowTitle("Test dans un cluster kind")
        self.resize(900, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Un cluster kind jetable reçoit le déploiement de l'environnement choisi, puis il est supprimé. "
                            "Avec le dossier du code (Dockerfile), l'image est construite et l'application doit répondre "
                            "en HTTP ; sans lui, les manifestes sont seulement soumis à l'API (dry-run serveur)."))
        form = QFormLayout()
        self.env = QComboBox()
        self.env.setAccessibleName("Environnement")
        project = result.ir.project
        for e in project.environments:
            self.env.addItem(e.display, e.id)
        dev = next((i for k in ("dev", "sandbox") for i, e in enumerate(project.environments) if e.kind == k), 0)
        self.env.setCurrentIndex(dev)
        form.addRow("Environnement", self.env)
        app_row = QHBoxLayout()
        self.app_dir = QLineEdit()
        self.app_dir.setPlaceholderText("facultatif : dossier contenant le Dockerfile")
        self.app_dir.setAccessibleName("Dossier du code")
        browse = QPushButton(icon("mdi6.folder-open-outline"), "Choisir…")
        browse.clicked.connect(self._browse)
        app_row.addWidget(self.app_dir, 1)
        app_row.addWidget(browse)
        form.addRow("Code de l'application", app_row)
        self.keep = QCheckBox("Garder le cluster après le test")
        form.addRow("", self.keep)
        lay.addLayout(form)
        tools = list(self.TOOLS) + (["helm"] if any(f.startswith("charts/") for f in result.files) else [])
        self.missing = [t for t in tools if shutil.which(t) is None]
        self.state = muted("Outils manquants : " + ", ".join(self.missing) if self.missing else "Outils présents : "
                           + ", ".join(tools))
        if self.missing:
            self.state.setStyleSheet(f"color: {theme.current().blocking};")
        lay.addWidget(self.state)
        self.log = QPlainTextEdit()
        self.log.setObjectName("codePreview")
        self.log.setReadOnly(True)
        self.log.setAccessibleName("Journal du test")
        lay.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.run_btn = QPushButton(icon("mdi6.play-circle-outline"), "Lancer le test")
        self.run_btn.setProperty("class", "success")
        self.run_btn.setEnabled(not self.missing)
        self.run_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton(icon("mdi6.stop-circle-outline"), "Arrêter")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        row.addWidget(self.run_btn)
        row.addWidget(self.stop_btn)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier du code de l'application", self.app_dir.text())
        if d:
            self.app_dir.setText(d)

    def start(self) -> None:
        if self.proc is not None:
            return
        root = Path(self.tmp.name) / "depot"
        if root.exists():
            shutil.rmtree(root)
        self.result.write(root)
        env = QProcessEnvironment.systemEnvironment()
        if self.app_dir.text().strip():
            env.insert("APP_DIR", self.app_dir.text().strip())
        if self.keep.isChecked():
            env.insert("KEEP_CLUSTER", "1")
        self.log.clear()
        self.exit_code = None
        self.proc = QProcess(self)
        self.proc.setProcessEnvironment(env)
        self.proc.setWorkingDirectory(str(root))
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.start("bash", [str(root / KIND_TEST), self.env.currentData()])
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _read(self) -> None:
        if self.proc is not None:
            text = bytes(self.proc.readAllStandardOutput().data()).decode("utf-8", errors="replace")
            self.log.insertPlainText(text)
            self.log.ensureCursorVisible()

    def _finished(self, code: int, _status) -> None:
        self._read()
        self.exit_code = code
        self.proc = None
        self.run_btn.setEnabled(not self.missing)
        self.stop_btn.setEnabled(False)
        verdict = "Test réussi." if code == 0 else f"Test en échec (code {code})."
        self.log.appendPlainText(f"\n{verdict}")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()  # le script supprime le cluster sur SIGTERM (trap EXIT)
            if not self.proc.waitForFinished(15000):
                self.proc.kill()

    def done(self, r: int) -> None:  # noqa: D401 (fermeture : arrêter le test en cours)
        self.stop()
        self.tmp.cleanup()
        super().done(r)
