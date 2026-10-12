# SPDX-License-Identifier: Apache-2.0
"""Export : différences avant écriture dans un dossier, et export vers un dépôt Git."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import gitexport, sync
from ..generators import GenerationResult
from . import theme
from .widgets import icon, muted

STATUS_ICONS = {
    sync.NEW: "mdi6.file-plus-outline", sync.UPDATED: "mdi6.file-sync-outline", sync.SAME: "mdi6.file-check-outline",
    sync.EDITED: "mdi6.file-alert-outline", sync.FOREIGN: "mdi6.file-question-outline",
    sync.OBSOLETE: "mdi6.file-remove-outline",
}


class DiffHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:  # noqa: N802 (API Qt)
        p = theme.current()
        fmt = QTextCharFormat()
        if text.startswith(("+++", "---")):
            fmt.setForeground(theme.qcolor(p.text_muted))
        elif text.startswith("+"):
            fmt.setForeground(theme.qcolor(p.ok))
            fmt.setBackground(theme.qcolor(p.ok, 28))
        elif text.startswith("-"):
            fmt.setForeground(theme.qcolor(p.blocking))
            fmt.setBackground(theme.qcolor(p.blocking, 28))
        elif text.startswith("@@"):
            fmt.setForeground(theme.qcolor(p.info))
        else:
            return
        self.setFormat(0, len(text), fmt)


class ChangesView(QWidget):
    """Liste des fichiers à écrire, avec case à cocher et différences du fichier sélectionné."""

    selectionChanged = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.changes: list[sync.FileChange] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.summary = muted("")
        self.hide_same = QCheckBox("Masquer les fichiers identiques")
        self.hide_same.setChecked(True)
        self.hide_same.toggled.connect(self._fill)
        top.addWidget(self.summary, 1)
        top.addWidget(self.hide_same)
        lay.addLayout(top)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Fichier", "État", "Lignes"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAccessibleName("Fichiers à écrire")
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.currentItemChanged.connect(self._show)
        self.tree.itemChanged.connect(self._toggled)
        split.addWidget(self.tree)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.help = muted("")
        rl.addWidget(self.help)
        self.diff = QPlainTextEdit()
        self.diff.setObjectName("codePreview")
        self.diff.setReadOnly(True)
        self.diff.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.diff.setAccessibleName("Différences du fichier")
        self.highlighter = DiffHighlighter(self.diff.document())
        rl.addWidget(self.diff, 1)
        split.addWidget(right)
        split.setSizes([500, 560])
        self.tree.setColumnWidth(0, 300)
        lay.addWidget(split, 1)

    def set_changes(self, changes: list[sync.FileChange]) -> None:
        self.changes = changes
        self._fill()

    def _fill(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        first = None
        for ch in self.changes:
            if ch.status == sync.SAME and self.hide_same.isChecked():
                continue
            added, removed = ch.stats()
            lines = "" if ch.status == sync.SAME else f"+{added} −{removed}"
            item = QTreeWidgetItem([ch.path, ch.status, lines])
            item.setIcon(0, icon(STATUS_ICONS[ch.status]))
            item.setData(0, Qt.ItemDataRole.UserRole, ch.path)
            item.setToolTip(1, sync.STATUS_HELP[ch.status])
            if ch.status != sync.SAME:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked if ch.selected else Qt.CheckState.Unchecked)
            if ch.status in (sync.EDITED, sync.FOREIGN):
                item.setForeground(1, theme.qcolor(theme.current().warning))
            self.tree.addTopLevelItem(item)
            if first is None and ch.status != sync.SAME:
                first = item
        self.tree.blockSignals(False)
        if first is not None:
            self.tree.setCurrentItem(first)
        else:
            self.diff.setPlainText("Aucun changement : les fichiers sont déjà à jour.")
        self._summary()

    def _summary(self) -> None:
        n = len(self.selected())
        self.summary.setText(f"{sync.describe(self.changes) or 'aucun fichier'} — {n} fichier(s) à écrire")
        self.selectionChanged.emit()

    def _change(self, path: str | None) -> sync.FileChange | None:
        return next((c for c in self.changes if c.path == path), None)

    def _show(self, item: QTreeWidgetItem | None) -> None:
        ch = self._change(item.data(0, Qt.ItemDataRole.UserRole)) if item else None
        if ch is None:
            return
        self.help.setText(sync.STATUS_HELP[ch.status]
                          + (" Cocher le fichier pour le remplacer quand même." if ch.status in (sync.EDITED, sync.FOREIGN)
                             else " Cocher le fichier pour le supprimer." if ch.deletion else ""))
        self.diff.setPlainText(ch.diff() or ch.new or "")

    def _toggled(self, item: QTreeWidgetItem, column: int) -> None:
        ch = self._change(item.data(0, Qt.ItemDataRole.UserRole))
        if ch is not None and column == 0:
            ch.selected = item.checkState(0) == Qt.CheckState.Checked
            self._summary()

    def selected(self) -> list[sync.FileChange]:
        return [c for c in self.changes if c.selected and c.status != sync.SAME]


class SyncDialog(QDialog):
    """Différences avec un dossier existant, puis écriture des fichiers choisis."""

    def __init__(self, result: GenerationResult, target: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.result, self.target = result, target
        self.written: list[str] = []
        self.setWindowTitle(f"Écrire dans {target}")
        self.resize(1100, 680)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Les fichiers retouchés à la main depuis la dernière génération, ou absents des générations "
                            "précédentes, ne sont pas cochés : ils ne sont remplacés que si vous le demandez."))
        self.view = ChangesView()
        self.view.set_changes(sync.plan(result.files, target))
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.write_btn = QPushButton(icon("mdi6.content-save-all-outline"), "Écrire la sélection")
        self.write_btn.setProperty("class", "success")
        cancel = QPushButton("Annuler")
        self.write_btn.clicked.connect(self._write)
        cancel.clicked.connect(self.reject)
        row.addWidget(self.write_btn)
        row.addWidget(cancel)
        lay.addLayout(row)
        self.view.selectionChanged.connect(lambda: self.write_btn.setEnabled(bool(self.view.selected())))
        self.write_btn.setEnabled(bool(self.view.selected()))

    def _write(self) -> None:
        self.written = sync.apply(self.view.changes, self.target)
        self.accept()


class _ExportThread(QThread):
    progress = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, changes, root, opts):
        super().__init__()
        self.changes, self.root, self.opts = changes, root, opts

    def run(self) -> None:
        try:
            out = gitexport.export(self.changes, self.root, self.opts, log=self.progress.emit)
        except gitexport.GitError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # erreur inattendue : affichée plutôt que perdue dans le fil
            self.failed.emit(f"Erreur inattendue : {exc}")
        else:
            self.finished_ok.emit(out)


class GitExportDialog(QDialog):
    """Committe les fichiers sur une nouvelle branche, pousse et ouvre la demande de fusion."""

    def __init__(self, result: GenerationResult, parent: QWidget | None = None, repo: str | None = None):
        super().__init__(parent)
        self.result = result
        self.info: gitexport.RepoInfo | None = None
        self.worker: _ExportThread | None = None
        self.outcome: gitexport.ExportOutcome | None = None
        self.setWindowTitle("Exporter vers un dépôt Git")
        self.resize(1100, 760)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Les fichiers sont committés sur une nouvelle branche ; votre branche courante n'est pas "
                            "modifiée. La demande de fusion est ouverte quand la forge le permet."))
        form = QFormLayout()
        repo_row = QHBoxLayout()
        self.repo = QLineEdit(repo or "")
        self.repo.setPlaceholderText("Copie de travail du dépôt de l'application")
        self.repo.setAccessibleName("Dépôt Git")
        browse = QPushButton(icon("mdi6.folder-open-outline"), "Choisir…")
        browse.clicked.connect(self._browse)
        repo_row.addWidget(self.repo, 1)
        repo_row.addWidget(browse)
        form.addRow("Dépôt", repo_row)
        self.repo_state = muted("")
        form.addRow("", self.repo_state)
        self.branch = QLineEdit(gitexport.default_branch_name())
        self.branch.setAccessibleName("Nouvelle branche")
        name = result.ir.project.name
        self.message = QLineEdit(f"Pipeline DevOps Builder : {name}")
        self.message.setAccessibleName("Message de commit")
        self.title = QLineEdit(f"Pipeline DevOps Builder — {name}")
        self.title.setAccessibleName("Titre de la demande de fusion")
        form.addRow("Nouvelle branche", self.branch)
        form.addRow("Message de commit", self.message)
        form.addRow("Titre de la demande", self.title)
        self.push = QCheckBox("Pousser la branche")
        self.push.setChecked(True)
        self.request = QCheckBox("Ouvrir une demande de fusion")
        self.request.setChecked(True)
        self.push.toggled.connect(self.request.setEnabled)
        opts = QHBoxLayout()
        opts.addWidget(self.push)
        opts.addWidget(self.request)
        opts.addStretch(1)
        form.addRow("", opts)
        lay.addLayout(form)
        self.view = ChangesView()
        lay.addWidget(self.view, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.log.setAccessibleName("Journal de l'export")
        self.log.hide()
        lay.addWidget(self.log)
        self.link = QLabel()
        self.link.setTextFormat(Qt.TextFormat.RichText)
        self.link.setOpenExternalLinks(False)
        self.link.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.link.setWordWrap(True)
        lay.addWidget(self.link)
        row = QHBoxLayout()
        row.addStretch(1)
        self.go = QPushButton(icon("mdi6.source-branch-plus"), "Committer et pousser")
        self.go.setProperty("class", "success")
        self.go.clicked.connect(self.start)
        self.close_btn = QPushButton("Fermer")
        self.close_btn.clicked.connect(self.accept)
        row.addWidget(self.go)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.push.toggled.connect(lambda on: self.go.setText("Committer et pousser" if on else "Committer"))
        self.repo.editingFinished.connect(self.load_repo)
        self.view.selectionChanged.connect(self._update_go)
        self.load_repo()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Copie de travail du dépôt", self.repo.text())
        if d:
            self.repo.setText(d)
            self.load_repo()

    def load_repo(self) -> None:
        self.info = None
        path = self.repo.text().strip()
        if not path:
            self.repo_state.setText("Choisir la copie de travail locale du dépôt de l'application.")
            self.view.set_changes([])
            self._update_go()
            return
        try:
            info = gitexport.inspect(path)
        except gitexport.GitError as exc:
            self.repo_state.setText(str(exc))
            self.view.set_changes([])
            self._update_go()
            return
        self.info = info
        remote = info.default_remote
        parts = [f"Branche « {info.branch or 'HEAD détachée'} »"]
        if remote:
            url = info.remotes[remote]
            forge = gitexport.forge_of(gitexport.parse_remote(url), self._project_forge())
            parts.append(f"distant {remote} : {url}" + (f" ({gitexport.FORGE_LABELS.get(forge, forge)})" if forge else ""))
        else:
            parts.append("aucun dépôt distant : commit local uniquement")
        if not info.has_commits:
            parts.append("dépôt vide : premier commit sur la branche courante, sans demande de fusion")
        if info.dirty:
            parts.append(f"⚠ {len(info.dirty)} fichier(s) modifié(s) non commité(s) : à committer ou mettre de côté d'abord")
        self.repo_state.setText(" · ".join(parts))
        self.push.setEnabled(bool(remote))
        if not remote:
            self.push.setChecked(False)
        self.view.set_changes(sync.plan(self.result.files, info.root))
        self._update_go()

    def _project_forge(self) -> str | None:
        forge = self.result.ir.forge
        return forge.forge if forge else None

    def _update_go(self) -> None:
        ready = (self.info is not None and not self.info.dirty and bool(self.view.selected()) and self.worker is None
                 and self.outcome is None)
        self.go.setEnabled(ready)

    def options(self) -> gitexport.ExportOptions:
        return gitexport.ExportOptions(
            branch=self.branch.text().strip(), message=self.message.text().strip() or "Pipeline DevOps Builder",
            title=self.title.text().strip() or "Pipeline DevOps Builder",
            description=gitexport.describe_changes(self.view.changes),
            push=self.push.isChecked(), open_request=self.request.isChecked() and self.push.isChecked(),
            forge=self._project_forge())

    def start(self) -> None:
        if self.info is None or self.worker is not None:
            return
        self.outcome = None
        self.log.clear()
        self.log.show()
        self.link.clear()
        self.worker = _ExportThread(self.view.changes, self.info.root, self.options())
        self.worker.progress.connect(self.log.appendPlainText)
        self.worker.finished_ok.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._thread_over)
        self._update_go()
        self.close_btn.setEnabled(False)
        self.worker.start()

    def _thread_over(self) -> None:
        self.worker = None
        self.close_btn.setEnabled(True)
        if self.outcome is not None:
            # Export fait : la liste reste celle des fichiers envoyés ; un nouvel export repart du dépôt.
            self.go.setText("Exporté")
            self.go.setEnabled(False)
            self.repo.editingFinished.connect(self._reset_after_export)
        else:
            self.load_repo()

    def _reset_after_export(self) -> None:
        self.repo.editingFinished.disconnect(self._reset_after_export)
        self.outcome = None
        self.go.setText("Committer et pousser" if self.push.isChecked() else "Committer")
        self.load_repo()

    def _done(self, out: gitexport.ExportOutcome) -> None:
        self.outcome = out
        self.log.appendPlainText(f"Commit {out.commit} sur « {out.branch} » : {len(out.files)} fichier(s).")
        for m in out.messages:
            self.log.appendPlainText(m)
        if out.request_url:
            verb = "Demande de fusion créée" if out.request_created else "Créer la demande de fusion"
            self.link.setText(f"<b>{verb} :</b> <a href='{out.request_url}'>{out.request_url}</a>")
        elif out.pushed:
            self.link.setText(f"<b>Branche poussée :</b> {out.branch}")
        self.branch.setText(gitexport.default_branch_name())

    def _failed(self, message: str) -> None:
        self.log.appendPlainText(message)
        self.link.setText(f"<span style='color:{theme.current().blocking}'><b>Export impossible.</b></span> "
                          "Le détail est dans le journal ci-dessus.")

    def reject(self) -> None:
        if self.worker is not None:
            QMessageBox.information(self, "Export en cours", "Attendre la fin de l'export avant de fermer.")
            return
        super().reject()
