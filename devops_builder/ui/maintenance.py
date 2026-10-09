"""Entretien du catalogue : contrôle des fiches, corrections, rafraîchissement du Landscape."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import catalog_edit, health, landscape, userdata
from ..catalog import Catalog
from ..model import Project
from . import theme
from .widgets import icon, muted

LEVEL_ICONS = {health.TO_FIX: "mdi6.alert-octagon", health.WATCH: "mdi6.alert", health.INFO: "mdi6.information"}


def _level_color(level: str) -> str:
    p = theme.current()
    return {health.TO_FIX: p.blocking, health.WATCH: p.warning, health.INFO: p.info}[level]


class _CheckThread(QThread):
    progressed = Signal(int, int)
    done = Signal(object)

    def __init__(self, catalog: Catalog, network: bool, refresh: bool):
        super().__init__()
        self.catalog, self.network, self.refresh = catalog, network, refresh

    def run(self) -> None:
        try:
            report = health.check_catalog(self.catalog, network=self.network, refresh=self.refresh,
                                          progress=self.progressed.emit)
        except Exception as exc:  # inattendu : rapport vide plutôt qu'un fil mort
            report = health.Report(network=self.network)
            report.findings.append(health.Finding("—", "Contrôle", "error", health.TO_FIX, f"erreur : {exc}"))
        self.done.emit(report)


class _RefreshThread(QThread):
    done = Signal(object, str)

    def __init__(self, source: str | None):
        super().__init__()
        self.source = source

    def run(self) -> None:
        try:
            diff, _path = landscape.refresh(self.source)
            self.done.emit(diff, "")
        except Exception as exc:
            self.done.emit(None, str(exc))


class MaintenanceDialog(QDialog):
    """Le catalogue est rechargé par la fenêtre principale quand `changed` est vrai."""

    def __init__(self, catalog: Catalog, project: Project | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.catalog, self.project = catalog, project
        self.report: health.Report | None = None
        self.worker: QThread | None = None
        self.changed = False
        self.setWindowTitle("Entretien du catalogue")
        self.resize(1080, 700)
        lay = QVBoxLayout(self)
        self.info = muted("")
        lay.addWidget(self.info)
        top = QHBoxLayout()
        self.network = QCheckBox("Interroger GitHub et GitLab (archivage, licence, activité)")
        self.network.setChecked(True)
        self.refresh_cache = QCheckBox("Ignorer le cache de 24 h")
        top.addWidget(self.network)
        top.addWidget(self.refresh_cache)
        top.addStretch(1)
        lay.addLayout(top)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        lay.addWidget(self.progress)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Fiche", "Constat", "Projet"])
        self.tree.setAccessibleName("Constats de l'entretien")
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.currentItemChanged.connect(self._show)
        self.tree.itemChanged.connect(lambda *_: self._update_buttons())
        split.addWidget(self.tree)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setAccessibleName("Détail du constat")
        split.addWidget(self.detail)
        split.setSizes([700, 360])
        lay.addWidget(split, 1)
        self.summary = muted("Le contrôle compare chaque fiche au Landscape et, en ligne, à son dépôt source.")
        lay.addWidget(self.summary)
        row = QHBoxLayout()
        self.run_btn = QPushButton(icon("mdi6.stethoscope"), "Lancer le contrôle")
        self.run_btn.setProperty("class", "success")
        self.run_btn.clicked.connect(self.start)
        self.apply_btn = QPushButton(icon("mdi6.check-all"), "Appliquer les corrections cochées")
        self.apply_btn.clicked.connect(self.apply)
        self.undo_btn = QPushButton(icon("mdi6.undo-variant"), "Retirer la correction")
        self.undo_btn.setToolTip("Rend à la fiche livrée ses valeurs d'origine")
        self.undo_btn.clicked.connect(self.undo_correction)
        self.export_btn = QPushButton(icon("mdi6.file-document-outline"), "Rapport…")
        self.export_btn.clicked.connect(self.export)
        row.addWidget(self.run_btn)
        row.addWidget(self.apply_btn)
        row.addWidget(self.undo_btn)
        row.addWidget(self.export_btn)
        row.addStretch(1)
        self.landscape_btn = QPushButton(icon("mdi6.cloud-download-outline"), "Rafraîchir le Landscape")
        self.landscape_btn.setToolTip("Télécharger le landscape.yml du CNCF et reconstruire l'index")
        self.landscape_btn.clicked.connect(lambda: self.refresh_landscape(None))
        self.reset_btn = QPushButton("Index livré")
        self.reset_btn.setToolTip("Revenir à l'index du Landscape livré avec l'application")
        self.reset_btn.clicked.connect(self.reset_landscape)
        folder = QPushButton(icon("mdi6.folder-open-outline"), "Dossier personnel")
        folder.clicked.connect(self.open_folder)
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        for b in (self.landscape_btn, self.reset_btn, folder, close):
            row.addWidget(b)
        lay.addLayout(row)
        self._update_info()
        self._update_buttons()

    # ------------------------------------------------------------- état
    def _update_info(self) -> None:
        idx = landscape.current_index_path()
        if idx == landscape.PACKAGED_INDEX:
            source = "index du Landscape livré avec l'application"
        else:
            when = datetime.fromtimestamp(idx.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            source = f"index du Landscape rafraîchi le {when}"
        users = len(self.catalog.user_tools())
        corrected = sum(1 for t in self.catalog.curated() if t.corrections)
        self.info.setText(f"{len(self.catalog.curated())} fiches, dont {users} personnelle(s) et {corrected} corrigée(s) · "
                          f"{source} · dossier personnel : {userdata.catalog_dir()}")
        self.reset_btn.setEnabled(idx != landscape.PACKAGED_INDEX)

    def _update_buttons(self) -> None:
        busy = self.worker is not None
        self.run_btn.setEnabled(not busy)
        self.landscape_btn.setEnabled(not busy)
        self.apply_btn.setEnabled(not busy and bool(self.checked_fixes()))
        self.export_btn.setEnabled(self.report is not None)
        tool = self._current_tool()
        self.undo_btn.setEnabled(not busy and tool is not None and bool(tool.corrections))

    def _current_tool(self):
        item = self.tree.currentItem()
        f = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        return self.catalog.get(f.tool_id) if isinstance(f, health.Finding) else None

    # ------------------------------------------------------------- contrôle
    def start(self) -> None:
        if self.worker is not None:
            return
        self.tree.clear()
        self.detail.clear()
        self.progress.setRange(0, 0)
        self.progress.setFormat("Contrôle des fiches…")
        self.progress.show()
        worker = _CheckThread(self.catalog, self.network.isChecked(), self.refresh_cache.isChecked())
        worker.progressed.connect(self._progress)
        worker.done.connect(self._done)
        worker.finished.connect(self._worker_over)
        self.worker = worker
        self._update_buttons()
        worker.start()

    def _progress(self, done: int, total: int) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.progress.setFormat(f"Dépôts interrogés : {done}/{total}")

    def _worker_over(self) -> None:
        self.worker = None
        self.progress.hide()
        self._update_buttons()

    def _done(self, report: health.Report) -> None:
        self.report = report
        self.tree.blockSignals(True)
        self.tree.clear()
        first = None
        for level in health.LEVELS:
            items = report.by_level(level)
            if not items:
                continue
            group = QTreeWidgetItem([f"{level.capitalize()} ({len(items)})", "", ""])
            group.setIcon(0, icon(LEVEL_ICONS[level], _level_color(level)))
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(group)
            for f in items:
                uses = health.affected_bricks(self.project, f) if self.project else 0
                item = QTreeWidgetItem([f.tool_name, f.message, str(uses) if uses else ""])
                item.setData(0, Qt.ItemDataRole.UserRole, f)
                item.setToolTip(1, f.message)
                if uses:
                    item.setToolTip(2, f"{uses} brique(s) du projet ouvert")
                if f.fix:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    # les corrections sûres sont cochées ; « relue aujourd'hui » demande une vraie relecture
                    item.setCheckState(0, Qt.CheckState.Checked if f.kind != "stale" else Qt.CheckState.Unchecked)
                group.addChild(item)
                first = first or item
            group.setExpanded(level != health.INFO or len(items) < 15)
        self.tree.blockSignals(False)
        if first is not None:
            self.tree.setCurrentItem(first)
        self.summary.setText(report.summary() + ("" if report.findings else " — rien à signaler."))
        if report.repos_failed and not health.github_token():
            self.summary.setText(self.summary.text() + " Un jeton GitHub (GITHUB_TOKEN ou gh auth login) lève la limite "
                                 "de 60 requêtes par heure.")
        self._update_buttons()

    def _show(self, item: QTreeWidgetItem | None) -> None:
        f = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(f, health.Finding):
            self.detail.clear()
            self._update_buttons()
            return
        tool = self.catalog.get(f.tool_id)
        lines = [f"{f.tool_name} ({f.tool_id})", f"{f.level} — {f.message}", ""]
        if tool is not None:
            from .properties import LIFECYCLE
            lic = "inconnue" if tool.license == "unknown" else tool.license
            state = "actif" if tool.lifecycle == "active" else LIFECYCLE.get(tool.lifecycle, tool.lifecycle).lower()
            lines.append(f"Fiche {'personnelle' if tool.origin == 'utilisateur' else 'livrée'}, "
                         f"licence {lic}, cycle de vie : {state}.")
            if tool.repo_url:
                lines.append(f"Dépôt : {tool.repo_url}")
            if tool.corrections:
                lines.append("Corrigée localement : " + ", ".join(
                    f"{k} (était {v!r})" for k, v in tool.corrections.items()))
        if f.fix:
            lines += ["", f"Correction proposée : {f.fix_label}", "  " + ", ".join(f"{k} = {v}" for k, v in f.fix.items())]
            if tool is not None and tool.origin == "livrée":
                lines.append("  (écrite dans corrections.yaml : les fichiers de l'application ne sont pas modifiés)")
        uses = health.affected_bricks(self.project, f) if self.project else 0
        if uses:
            lines += ["", f"Le projet ouvert utilise cette brique ({uses} fois) : ses diagnostics suivront la correction."]
        self.detail.setPlainText("\n".join(lines))
        self._update_buttons()

    def checked_fixes(self) -> list[tuple[str, dict]]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                item = group.child(j)
                f = item.data(0, Qt.ItemDataRole.UserRole)
                if f.fix and item.checkState(0) == Qt.CheckState.Checked:
                    out.append((f.tool_id, f.fix))
        return out

    # ------------------------------------------------------------- actions
    def _reload(self) -> None:
        from ..catalog import reload_default_catalog
        self.catalog = reload_default_catalog()
        self.changed = True
        self._update_info()

    def apply(self) -> None:
        fixes = self.checked_fixes()
        if not fixes:
            return
        try:
            changed = catalog_edit.apply_fixes(fixes, self.catalog)
        except ValueError as exc:
            QMessageBox.warning(self, "Correction refusée", str(exc))
            return
        self._reload()
        self.summary.setText(f"{len(changed)} fiche(s) corrigée(s) : {', '.join(changed)}. Relancer le contrôle pour vérifier.")
        self.tree.clear()
        self.report = None
        self._update_buttons()

    def undo_correction(self) -> None:
        tool = self._current_tool()
        if tool is None or not tool.corrections:
            return
        if catalog_edit.remove_correction(tool.id):
            self._reload()
            self.summary.setText(f"Correction de « {tool.name} » retirée : la fiche livrée reprend ses valeurs d'origine.")
            self._update_buttons()

    def export(self) -> None:
        if self.report is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Rapport d'entretien", "entretien-catalogue.md", "Markdown (*.md)")
        if path:
            Path(path).write_text(self.report.markdown(), encoding="utf-8")

    def refresh_landscape(self, source: str | None) -> None:
        if self.worker is not None:
            return
        self.progress.setRange(0, 0)
        self.progress.setFormat("Téléchargement du Landscape…")
        self.progress.show()
        worker = _RefreshThread(source)
        worker.done.connect(self._refreshed)
        worker.finished.connect(self._worker_over)
        self.worker = worker
        self._update_buttons()
        worker.start()

    def _refreshed(self, diff, error: str) -> None:
        if error:
            self.summary.setText(f"Rafraîchissement impossible : {error}")
            return
        self._reload()
        text = f"Landscape rafraîchi : {diff.summary()}."
        archived = [t.name for t in self.catalog.curated() if (t.landscape_name or t.name) in diff.newly_archived]
        if archived:
            text += f" Fiches concernées : {', '.join(archived)} — lancer le contrôle."
        self.summary.setText(text)

    def reset_landscape(self) -> None:
        if landscape.reset():
            self._reload()
            self.summary.setText("Index du Landscape livré rétabli.")

    def open_folder(self) -> None:
        folder = userdata.catalog_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def done(self, r: int) -> None:
        if self.worker is not None:
            self.worker.wait(60000)
        super().done(r)
