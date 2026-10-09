"""Fenêtre principale de DevOps Builder."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..catalog import DATA_DIR, Catalog
from ..generators import BlockingDiagnostics, generate
from ..model import ENVIRONMENTS, STAGE_IDS, STAGE_LABELS, TARGETS, Project, Severity
from ..rules import Action, RuleEngine, apply_action
from . import theme
from .canvas import PipelineCanvas
from .diagnostics import DiagnosticsPanel
from .dialogs import GenerateDialog, ProjectSettingsDialog, about_text
from .palette import PaletteWidget
from .properties import PropertiesPanel
from .widgets import STAGE_ICONS, chip, clear_layout, icon


def autosave_path() -> Path:
    from .. import userdata
    return userdata.home() / "autosave.devops.yaml"
FILE_FILTER = "Projet DevOps Builder (*.devops.yaml *.yaml)"


class SnapshotCommand(QUndoCommand):
    """Annuler / rétablir par instantanés YAML du projet : simple et sûr."""

    def __init__(self, window: MainWindow, before: str, after: str, text: str, first_props: bool = True):
        super().__init__(text)
        self.window, self.before, self.after = window, before, after
        self._first = True
        self._first_props = first_props

    def undo(self) -> None:
        self.window._restore(self.before)

    def redo(self) -> None:
        # Au premier passage d'une modification de paramètres, on ne reconstruit pas
        # le panneau Propriétés en cours d'édition.
        props = self._first_props or not self._first
        self._first = False
        self.window._restore(self.after, properties=props)


class MainWindow(QMainWindow):
    def __init__(self, catalog: Catalog, engine: RuleEngine, project: Project | None = None,
                 path: Path | None = None):
        super().__init__()
        self.catalog = catalog
        self.engine = engine
        self.project = project or Project()
        self.path = path
        self.selected: str | None = None
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(lambda _: self._update_title())
        self.settings = QSettings("DevOpsBuilder", "DevOpsBuilder")
        self.dark = self.settings.value("dark", False, type=bool)

        self.setWindowTitle("DevOps Builder")
        self.resize(1500, 920)
        self._build_central()
        self._build_docks()
        self._build_actions()
        self._build_toolbar_and_menus()
        self.statusBar().showMessage("Prêt", 3000)
        if self.catalog.errors:
            self.statusBar().showMessage(f"{len(self.catalog.errors)} erreur(s) dans le catalogue personnel : "
                                         "Catalogue › Entretien du catalogue pour le détail.", 15000)
        self.summary = QLabel()
        self.statusBar().addPermanentWidget(self.summary)
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.refresh()

    # ================================================================ UI
    def _build_central(self) -> None:
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.project_bar = QFrame()
        self.project_bar.setObjectName("projectBar")
        bar = QHBoxLayout(self.project_bar)
        bar.setContentsMargins(16, 10, 16, 10)
        self.title = QLabel()
        self.title.setObjectName("heroTitle")
        self.title.setMinimumWidth(120)
        self.title.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        bar.addWidget(self.title)
        self.app_btn = QPushButton()
        self.app_btn.setObjectName("appCard")
        self.app_btn.setToolTip("L'application mise en pipeline : dossier, analyse, langage, port")
        self.app_btn.setAccessibleName("Application")
        self.app_btn.clicked.connect(self.edit_application)
        bar.addWidget(self.app_btn)
        # Les puces prennent la place qui reste : sur un petit écran elles sont rognées au lieu
        # d'imposer à la fenêtre une largeur minimale plus grande que l'écran.
        self.chips_area = QScrollArea()
        self.chips_area.setFrameShape(QFrame.Shape.NoFrame)
        self.chips_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chips_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chips_area.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.chips_area.setFixedHeight(30)
        self.chips_area.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        chips = QWidget()
        self.chips_box = QHBoxLayout(chips)
        self.chips_box.setContentsMargins(0, 0, 0, 0)
        self.chips_box.setSpacing(6)
        self.chips_area.setWidgetResizable(True)  # le contenu garde sa largeur ; l'excédent est rogné
        self.chips_area.setWidget(chips)
        bar.addWidget(self.chips_area, 1)
        self.ports_btn = QPushButton("Ports")
        self.ports_btn.setToolTip("Ports de l'application et des briques, par environnement (Ctrl+Maj+P)")
        self.ports_btn.clicked.connect(self.show_ports)
        bar.addWidget(self.ports_btn)
        self.settings_btn = QPushButton()
        self.settings_btn.setToolTip("Paramètres du projet (F2)")
        self.settings_btn.setAccessibleName("Paramètres du projet")
        self.settings_btn.clicked.connect(lambda: self.edit_settings())
        bar.addWidget(self.settings_btn)
        self.generate_btn = QPushButton("Générer")
        self.generate_btn.setProperty("class", "success")
        self.generate_btn.clicked.connect(self.generate)
        bar.addWidget(self.generate_btn)
        lay.addWidget(self.project_bar)

        self.canvas = PipelineCanvas()
        self.canvas.selectionChanged.connect(self._select_brick)
        self.canvas.toolDropped.connect(self.add_tool)
        self.canvas.brickMoved.connect(self.move_brick)
        self.canvas.deleteRequested.connect(self.remove_brick)
        self.canvas.shiftRequested.connect(self.shift_brick)
        self.canvas.dropRefused.connect(self._explain_refusal)
        self.canvas.set_placement_check(self.catalog.can_place)
        lay.addWidget(self.canvas, 1)
        self.setCentralWidget(central)

    def _build_docks(self) -> None:
        self.palette = PaletteWidget(self.catalog)
        self.palette.toolActivated.connect(lambda tid: self.add_tool(None, tid, -1))
        self.palette.toolSelected.connect(self._show_catalog_tool)
        self.palette.tree.dragStarted.connect(self.canvas.highlight)
        self.palette.tree.dragFinished.connect(self.canvas.clear_highlight)
        self.palette.ficheRequested.connect(self.edit_fiche)
        self.palette.ficheDeleteRequested.connect(self.delete_fiche)
        self.palette_dock = self._dock("Catalogue", self.palette, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.palette_dock.setMinimumWidth(300)

        self.properties = PropertiesPanel(self.catalog)
        self.properties.paramsChanged.connect(self.set_params)
        self.properties.overridesChanged.connect(self.set_overrides)
        self.properties.removeRequested.connect(self.remove_brick)
        self.properties.addRequested.connect(lambda tid: self.add_tool(None, tid, -1))
        self.properties.ficheRequested.connect(self.edit_fiche)
        self.props_dock = self._dock("Propriétés", self.properties, Qt.DockWidgetArea.RightDockWidgetArea)
        self.props_dock.setMinimumWidth(320)

        self.diagnostics = DiagnosticsPanel()
        self.diagnostics.brickFocused.connect(self._focus_brick)
        self.diagnostics.actionRequested.connect(self.apply_fix)
        self.diag_dock = self._dock("Diagnostics", self.diagnostics, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.diag_dock.setMinimumHeight(190)

    def _dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock-{title}")
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(area, dock)
        return dock

    def _act(self, text: str, slot: Callable, shortcut: QKeySequence | str | None = None,
             icon_name: str | None = None, tip: str = "") -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if icon_name:
            a.setData(icon_name)
        a.setToolTip(tip or text)
        a.triggered.connect(slot)
        return a

    def _build_actions(self) -> None:
        K = QKeySequence.StandardKey
        self.a_new = self._act("Nouveau…", self.new_project, K.New, "mdi6.file-plus-outline",
                               "Nouveau projet avec l'assistant (Ctrl+N)")
        self.a_new_empty = self._act("Nouveau projet vide", self.new_empty_project, "Ctrl+Shift+N")
        self.a_open = self._act("Ouvrir…", self.open_project, K.Open, "mdi6.folder-open-outline")
        self.a_save = self._act("Enregistrer", self.save, K.Save, "mdi6.content-save-outline")
        self.a_save_as = self._act("Enregistrer sous…", self.save_as, K.SaveAs)
        self.a_generate = self._act("Générer les fichiers…", self.generate, "Ctrl+G", "mdi6.rocket-launch-outline",
                                    "Générer les fichiers du pipeline (Ctrl+G)")
        self.a_settings = self._act("Paramètres du projet…", self.edit_settings, "F2", "mdi6.cog-outline")
        self.a_ports = self._act("Ports et exposition…", self.show_ports, "Ctrl+Shift+P", "mdi6.lan",
                                 "Ports de l'application et des briques, par environnement (Ctrl+Maj+P)")
        self.a_application = self._act("Application…", self.edit_application, "Ctrl+Shift+A", "mdi6.application-cog-outline",
                                       "Dossier de l'application, analyse, langage et port (Ctrl+Maj+A)")
        self.a_validate = self._act("Valider…", self.validate, "Ctrl+Shift+V", "mdi6.check-decagram-outline",
                                    "Contrôler les fichiers générés avec les outils installés, puis tester dans kind (Ctrl+Maj+V)")
        self.a_undo = self.undo_stack.createUndoAction(self, "Annuler")
        self.a_undo.setShortcut(K.Undo)
        self.a_undo.setData("mdi6.undo")
        self.a_redo = self.undo_stack.createRedoAction(self, "Rétablir")
        self.a_redo.setShortcut(K.Redo)
        self.a_redo.setData("mdi6.redo")
        self.a_delete = self._act("Retirer la brique", lambda: self.selected and self.remove_brick(self.selected),
                                  None, "mdi6.delete-outline")
        self.a_theme = self._act("Thème sombre", self.toggle_theme, "Ctrl+T", "mdi6.theme-light-dark")
        self.a_theme.setCheckable(True)
        self.a_theme.setChecked(self.dark)
        self.a_search = self._act("Rechercher dans le catalogue", self._focus_search, "Ctrl+F")
        self.a_focus_canvas = self._act("Aller au pipeline", lambda: self.canvas.columns["source"].list.setFocus(), "Ctrl+2")
        self.a_focus_diag = self._act("Aller aux diagnostics", lambda: self.diagnostics.tree.setFocus(), "Ctrl+3")
        self.a_restore = self._act("Restaurer la sauvegarde automatique", self.restore_autosave)
        self.a_maintenance = self._act("Entretien du catalogue…", self.maintain_catalog, None, "mdi6.stethoscope",
                                       "Archivages, changements de licence, fiches à relire, Landscape à jour")
        self.a_new_fiche = self._act("Nouvelle fiche personnelle…", self.new_fiche, None, "mdi6.file-plus-outline")
        self.a_catalog_folder = self._act("Ouvrir le dossier du catalogue personnel", self.open_catalog_folder)
        self.a_about = self._act("À propos", self.about)
        self.a_rules = self._act("Règles de compatibilité", self.show_rules)
        for a in (self.a_search, self.a_focus_canvas, self.a_focus_diag):
            self.addAction(a)

    def _build_toolbar_and_menus(self) -> None:
        tb = QToolBar("Barre d'outils")
        tb.setObjectName("main-toolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for a in (self.a_new, self.a_open, self.a_save, None, self.a_undo, self.a_redo, None,
                  self.a_settings, self.a_generate, self.a_validate, None, self.a_theme):
            if a is None:
                tb.addSeparator()
            else:
                tb.addAction(a)
        self.addToolBar(tb)
        self.toolbar = tb

        mb = self.menuBar()
        m = mb.addMenu("&Fichier")
        m.addActions([self.a_new, self.a_new_empty, self.a_open])
        ex = m.addMenu("Ouvrir un exemple")
        for p in sorted((DATA_DIR / "examples").glob("*.yaml")):
            proj = Project.load(p)
            ex.addAction(proj.name, lambda checked=False, path=p: self.open_path(path, as_template=True))
        m.addSeparator()
        m.addActions([self.a_save, self.a_save_as])
        m.addSeparator()
        m.addAction(self.a_generate)
        m.addAction(self.a_restore)
        m.addSeparator()
        m.addAction("Quitter", self.close, QKeySequence.StandardKey.Quit)
        e = mb.addMenu("&Édition")
        e.addActions([self.a_undo, self.a_redo, self.a_delete])
        p = mb.addMenu("&Projet")
        p.addAction(self.a_application)
        p.addAction(self.a_settings)
        p.addAction(self.a_generate)
        p.addAction(self.a_validate)
        p.addAction(self.a_ports)
        c = mb.addMenu("&Catalogue")
        c.addActions([self.a_maintenance, self.a_new_fiche, self.a_catalog_folder])
        v = mb.addMenu("&Affichage")
        v.addAction(self.a_theme)
        v.addSeparator()
        for d in (self.palette_dock, self.props_dock, self.diag_dock):
            v.addAction(d.toggleViewAction())
        v.addSeparator()
        v.addActions([self.a_search, self.a_focus_canvas, self.a_focus_diag])
        h = mb.addMenu("&Aide")
        h.addActions([self.a_rules, self.a_about])
        self._update_icons()

    def _update_icons(self) -> None:
        for a in self.findChildren(QAction):
            name = a.data()
            if isinstance(name, str) and name.startswith("mdi6."):
                a.setIcon(icon(name))
        pal = theme.current()
        self.generate_btn.setIcon(icon("mdi6.rocket-launch-outline", pal.primary))
        self.settings_btn.setIcon(icon("mdi6.cog-outline", pal.text))
        self.ports_btn.setIcon(icon("mdi6.lan", pal.text))
        for sid, col in self.canvas.columns.items():
            col.findChild(QLabel).setPixmap(icon(STAGE_ICONS[sid], pal.primary).pixmap(20, 20))

    # ============================================================ état / rafraîchissement
    def refresh(self, properties: bool = True) -> None:
        diags = self.engine.evaluate(self.project)
        worst: dict[str, Severity] = {}
        for d in diags:
            for uid in d.bricks:
                if uid not in worst or d.severity.rank < worst[uid].rank:
                    worst[uid] = d.severity
        if self.selected and not self.project.find(self.selected):
            self.selected = None
        self.canvas.rebuild(self.project, self.catalog, {k: v.value for k, v in worst.items()}, self.selected)
        self.diagnostics.set_diagnostics(diags)
        self.palette.set_project(self.project)
        self._update_project_bar()
        self._update_title()
        blocking = sum(1 for d in diags if d.severity is Severity.BLOCKING)
        n = len(self.project.all_bricks())
        self.summary.setText(f"{n} brique{'s' if n > 1 else ''} · "
                             + (f"{blocking} erreur(s) bloquante(s)" if blocking else "aucune erreur bloquante"))
        self.generate_btn.setEnabled(n > 0)
        if properties:
            self._show_selected()

    def _update_project_bar(self) -> None:
        from .application import LANGUAGE_ICONS, app_label
        p = self.project
        self.title.setText(p.name)
        name = p.app.image_name if len(p.app.image_name) <= 22 else p.app.image_name[:21] + "…"
        self.app_btn.setText(f"{name} :{p.app.port}" + ("" if p.app.source else " · dossier ?"))
        self.app_btn.setIcon(icon(LANGUAGE_ICONS.get(p.app.language, "mdi6.application-outline"), theme.current().primary))
        self.app_btn.setToolTip(f"Application {app_label(p)}\nDossier : {p.app.source}" if p.app.source
                                else f"Application {app_label(p)}\nDésigner son dossier pour l'analyser (Ctrl+Maj+A)")
        clear_layout(self.chips_box)
        self.chips_box.addWidget(chip(TARGETS[p.target], primary=True, tooltip="Cible d'hébergement"))
        for i, env in enumerate(p.environments):
            if i:
                arrow = QLabel("→")
                arrow.setObjectName("muted")
                arrow.setAccessibleName("puis")
                self.chips_box.addWidget(arrow)
            text = env.display + (" · approbation" if env.approval else "")
            tip = f"Environnement {env.id} ({ENVIRONMENTS[env.kind]})"
            if env.host:
                tip += f" · hôte partagé « {env.host} »"
            self.chips_box.addWidget(chip(text, primary=env.kind == "production", tooltip=tip))
        self.chips_box.addWidget(chip("OIDC" if p.cloud_auth == "oidc" else "Clés statiques",
                                      tooltip="Authentification cloud en CI"))
        if p.secnumcloud:
            self.chips_box.addWidget(chip("SecNumCloud", primary=True))
        if p.license_policy == "oss-only":
            self.chips_box.addWidget(chip("Open source uniquement"))
        self.chips_box.addStretch(1)
        width = sum(self.chips_box.itemAt(i).widget().sizeHint().width() + self.chips_box.spacing()
                    for i in range(self.chips_box.count()) if self.chips_box.itemAt(i).widget())
        self.chips_area.widget().setMinimumWidth(width)
        envs = " → ".join(e.display for e in p.environments)
        self.project_bar.setToolTip(f"{TARGETS[p.target]} · {envs}")

    def _update_title(self) -> None:
        name = self.path.name if self.path else "sans titre"
        star = "" if self.undo_stack.isClean() else " •"
        self.setWindowTitle(f"{self.project.name} — {name}{star} — DevOps Builder")

    def _show_selected(self) -> None:
        if self.selected:
            found = self.project.find(self.selected)
            if found:
                tool = self.catalog.get(found[2].tool)
                if tool:
                    self.properties.show_tool(tool, found[2], self.project)
                    return
        self.properties.show_empty()

    def _restore(self, text: str, properties: bool = True) -> None:
        self.project = Project.from_yaml(text)
        self._autosave()
        if properties:
            self.refresh()
        else:
            QTimer.singleShot(0, lambda: self.refresh(properties=False))

    def mutate(self, label: str, fn: Callable[[Project], object], properties: bool = True) -> None:
        before = self.project.to_yaml()
        work = self.project.clone()
        fn(work)
        after = work.to_yaml()
        if after != before:
            self.undo_stack.push(SnapshotCommand(self, before, after, label, first_props=properties))

    def _autosave(self) -> None:
        try:
            autosave_path().parent.mkdir(parents=True, exist_ok=True)
            autosave_path().write_text(self.project.to_yaml(), encoding="utf-8")
        except OSError:
            pass

    # ============================================================ actions sur les briques
    def add_tool(self, stage: str | None, tool_id: str, index: int = -1) -> None:
        tool = self.catalog.get(tool_id)
        if tool is None:
            return
        existing = self.project.bricks_for(tool_id)
        if existing:
            self.selected = existing[0].uid
            self.statusBar().showMessage(f"{tool.name} est déjà dans le pipeline.", 4000)
            self.refresh()
            self.canvas.select(self.selected)
            return
        target_stage = stage or tool.stage
        if not tool.can_go_in(target_stage):
            self._explain_refusal(tool_id, target_stage)
            return

        def do(p: Project) -> None:
            b = p.add(tool_id, target_stage, None if index is None or index < 0 else index)
            self.selected = b.uid

        self.mutate(f"Ajouter {tool.name}", do)

    def move_brick(self, uid: str, stage: str, index: int) -> None:
        found = self.project.find(uid)
        if not found:
            return
        src_stage, src_idx, brick = found
        if not self.catalog.can_place(brick.tool, stage):
            self._explain_refusal(brick.tool, stage)
            return
        if src_stage == stage and index > src_idx:
            index -= 1
        self.selected = uid
        self.mutate("Déplacer la brique", lambda p: p.move(uid, stage, index))

    def shift_brick(self, uid: str, delta: int) -> None:
        found = self.project.find(uid)
        if not found:
            return
        tool = self.catalog.get(found[2].tool)
        if tool is None:
            return
        here = STAGE_IDS.index(found[0])
        # Étape autorisée la plus proche dans la direction demandée.
        candidates = [s for s in tool.allowed_stages
                      if (STAGE_IDS.index(s) > here if delta > 0 else STAGE_IDS.index(s) < here)]
        if not candidates:
            where = "à droite" if delta > 0 else "à gauche"
            self.statusBar().showMessage(
                f"{tool.name} n'a pas d'autre étape possible {where} "
                f"(étapes : {', '.join(STAGE_LABELS[s] for s in tool.allowed_stages)}).", 5000)
            return
        dest = candidates[0] if delta > 0 else candidates[-1]
        self.selected = uid
        self.mutate("Déplacer la brique", lambda p: p.move(uid, dest))
        self.canvas.select(uid)

    def _explain_refusal(self, tool_id: str, stage: str) -> None:
        tool = self.catalog.get(tool_id)
        if tool is None:
            return
        allowed = ", ".join(f"« {STAGE_LABELS[s]} »" for s in tool.allowed_stages)
        self.statusBar().showMessage(
            f"{tool.name} ne peut pas aller dans « {STAGE_LABELS[stage]} » : étapes possibles {allowed}.", 6000)

    def remove_brick(self, uid: str) -> None:
        found = self.project.find(uid)
        if not found:
            return
        tool = self.catalog.get(found[2].tool)
        self.mutate(f"Retirer {tool.name if tool else found[2].tool}", lambda p: p.remove(uid))
        self.statusBar().showMessage("Brique retirée — Ctrl+Z pour annuler.", 4000)

    def set_overrides(self, env_id: str, tool_id: str, params: dict) -> None:
        def do(p: Project) -> None:
            env = p.env(env_id)
            if env is None:
                return
            if params:
                env.overrides[tool_id] = params
            else:
                env.overrides.pop(tool_id, None)
        self.mutate("Modifier une surcharge d'environnement", do, properties=False)

    def set_params(self, uid: str, params: dict) -> None:
        def do(p: Project) -> None:
            f = p.find(uid)
            if f:
                f[2].params = params
        self.mutate("Modifier les paramètres", do, properties=False)

    def apply_fix(self, action: Action) -> None:
        self.mutate(action.label, lambda p: apply_action(p, action, self.catalog))
        self.statusBar().showMessage(f"Correction appliquée : {action.label} — Ctrl+Z pour annuler.", 5000)

    def _select_brick(self, uid: str) -> None:
        self.selected = uid
        self._show_selected()

    def _focus_brick(self, uid: str) -> None:
        self.selected = uid
        self.canvas.select(uid)
        self._show_selected()

    def _show_catalog_tool(self, tool_id: str) -> None:
        tool = self.catalog.get(tool_id)
        if tool:
            existing = self.project.bricks_for(tool_id)
            self.properties.show_tool(tool, existing[0] if existing else None, self.project)

    # ============================================================ catalogue
    def reload_catalog(self, catalog: Catalog | None = None) -> None:
        """Après une fiche créée, corrigée ou supprimée : règles, palette et fiche affichée suivent."""
        from ..catalog import reload_default_catalog
        self.catalog = catalog or reload_default_catalog()
        self.engine = RuleEngine(self.catalog)
        self.palette.catalog = self.catalog
        self.properties.catalog = self.catalog
        self.canvas.set_placement_check(self.catalog.can_place)
        self.palette.refresh()
        self.refresh()

    def maintain_catalog(self) -> None:
        from .maintenance import MaintenanceDialog
        dlg = MaintenanceDialog(self.catalog, self.project, self)
        dlg.exec()
        if dlg.changed:
            self.reload_catalog(dlg.catalog)

    def new_fiche(self) -> None:
        from .fiche import FicheDialog
        dlg = FicheDialog(self.catalog, {"id": "", "name": "", "stage": "build", "license": "unknown",
                                         "verified": date.today().isoformat()}, parent=self)
        if dlg.exec() and dlg.saved_id:
            self.reload_catalog()
            self._show_catalog_tool(dlg.saved_id)

    def edit_fiche(self, tool_id: str) -> None:
        from .fiche import open_fiche_dialog
        tool = self.catalog.get(tool_id)
        if tool is None:
            return
        dlg = open_fiche_dialog(self, self.catalog, tool)
        if not dlg.exec() or not dlg.saved_id:
            return
        new_id, old_ids = dlg.saved_id, {dlg.source_entry, dlg.editing} - {None, dlg.saved_id}
        self.reload_catalog()
        if old_ids and any(self.project.bricks_for(o) for o in old_ids):
            def do(p: Project) -> None:
                for _, b in p.all_bricks():
                    if b.tool in old_ids:
                        b.tool = new_id
            self.mutate("Briques rattachées à la nouvelle fiche", do)
        self._show_catalog_tool(new_id)
        self.statusBar().showMessage(f"Fiche « {new_id} » enregistrée dans le catalogue personnel.", 6000)

    def delete_fiche(self, tool_id: str) -> None:
        from .. import catalog_edit
        tool = self.catalog.get(tool_id)
        if tool is None or tool.origin != "utilisateur":
            return
        uses = len(self.project.bricks_for(tool_id))
        warn = f"\n\nLe projet ouvert l'utilise {uses} fois : ces briques deviendront inconnues." if uses else ""
        r = QMessageBox.question(self, "Supprimer la fiche",
                                 f"Supprimer la fiche personnelle « {tool.name} » ?{warn}")
        if r == QMessageBox.StandardButton.Yes:
            catalog_edit.delete_fiche(tool_id)
            self.reload_catalog()

    def open_catalog_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from .. import userdata
        folder = userdata.catalog_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _focus_search(self) -> None:
        self.palette_dock.show()
        self.palette.search.setFocus()
        self.palette.search.selectAll()

    # ============================================================ projet / fichiers
    def edit_settings(self, tab: str = "") -> None:
        dlg = ProjectSettingsDialog(self.project, self, self.catalog)
        if tab == "environnements":
            dlg.tabs.setCurrentWidget(dlg.envs_editor)
        if dlg.exec():
            self.mutate("Paramètres du projet", dlg.apply_to)

    def edit_application(self) -> None:
        from .application import ApplicationDialog
        dlg = ApplicationDialog(self.project, self.catalog, self)
        if dlg.exec():
            self.mutate("Application", dlg.apply_to)

    def show_ports(self) -> None:
        from .ports import PortsDialog

        def edit() -> Project:
            self.edit_settings("environnements")
            return self.project
        PortsDialog(self.project, self.catalog, self, edit_environments=edit).exec()

    def _confirm_discard(self) -> bool:
        if self.undo_stack.isClean():
            return True
        r = QMessageBox.question(self, "Modifications non enregistrées",
                                 "Enregistrer les modifications du projet en cours ?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def new_project(self) -> None:
        """Nouveau projet guidé par l'assistant."""
        if not self._confirm_discard():
            return
        from .wizard import StarterWizard
        wizard = StarterWizard(self.catalog, self.engine, self)
        if wizard.exec():
            self._load(wizard.project(), None)
            self.statusBar().showMessage("Projet créé par l'assistant : tout reste modifiable.", 5000)

    def new_empty_project(self) -> None:
        if self._confirm_discard():
            self._load(Project(), None)

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un projet", str(Path.home()), FILE_FILTER)
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path, as_template: bool = False) -> None:
        if as_template and not self._confirm_discard():
            return
        try:
            project = Project.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Ouverture impossible", f"{path.name} n'est pas un projet valide :\n{exc}")
            return
        self._load(project, None if as_template else path)

    def _load(self, project: Project, path: Path | None) -> None:
        self.project = project
        self.path = path
        self.selected = None
        self.undo_stack.clear()
        self.refresh()
        self.canvas.horizontalScrollBar().setValue(0)

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        self.project.save(self.path)
        self.undo_stack.setClean()
        self.statusBar().showMessage(f"Enregistré dans {self.path}", 4000)
        return True

    def save_as(self) -> bool:
        default = str(Path.home() / f"{self.project.app.image_name or 'projet'}.devops.yaml")
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le projet", default, FILE_FILTER)
        if not path:
            return False
        if not path.endswith((".yaml", ".yml")):
            path += ".devops.yaml"
        self.path = Path(path)
        return self.save()

    def restore_autosave(self) -> None:
        if not autosave_path().exists():
            QMessageBox.information(self, "Sauvegarde automatique", "Aucune sauvegarde automatique.")
            return
        if self._confirm_discard():
            self._load(Project.load(autosave_path()), None)

    def _generation(self):
        if not self.project.all_bricks():
            return None
        try:
            return generate(self.project, self.catalog, self.engine)
        except BlockingDiagnostics as exc:
            lines = "\n".join(f"• {d.rule_id} — {d.message}" for d in exc.diagnostics[:8])
            QMessageBox.warning(self, "Génération bloquée",
                                f"Corrigez d'abord ces erreurs bloquantes (panneau Diagnostics) :\n\n{lines}")
            self.diag_dock.show()
            self.diagnostics.tree.setFocus()
            return None

    def generate(self) -> None:
        result = self._generation()
        if result is not None:
            GenerateDialog(result, self).exec()

    def validate(self) -> None:
        result = self._generation()
        if result is not None:
            from .validation import ValidationDialog
            ValidationDialog(result, self).exec()

    def toggle_theme(self) -> None:
        self.dark = not self.dark
        self.a_theme.setChecked(self.dark)
        self.settings.setValue("dark", self.dark)
        theme.apply(QApplication.instance(), self.dark)  # type: ignore[arg-type]
        self._update_icons()
        self.palette.refresh()
        self.refresh()

    def show_rules(self) -> None:
        rows = "".join(f"<tr><td><b>{r.id}</b></td><td>{r.severity.label}</td><td>{r.title}</td></tr>"
                       for r in self.engine.rules)
        box = QMessageBox(self)
        box.setWindowTitle("Règles de compatibilité")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(f"<table cellspacing='6'>{rows}</table>")
        box.exec()

    def about(self) -> None:
        QMessageBox.about(self, "À propos", about_text(len(self.catalog.curated()), len(self.catalog.tools),
                                                         len(self.engine.rules)))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._confirm_discard():
            self.settings.setValue("geometry", self.saveGeometry())
            event.accept()
        else:
            event.ignore()
