# SPDX-License-Identifier: Apache-2.0
"""Canevas du pipeline : une carte par étape, des briques glissables."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QMimeData, QModelIndex, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..catalog import Catalog
from ..model import STAGES, SUPPORT, Project
from . import theme
from .a11y import DecorativeIcon
from .palette import MIME_TOOL
from .widgets import KIND_ICONS, SEVERITY_ICONS, STAGE_ICONS, icon

MIME_BRICK = "application/x-devops-brick"
R_UID = Qt.ItemDataRole.UserRole
R_NAME = Qt.ItemDataRole.UserRole + 1
R_SUB = Qt.ItemDataRole.UserRole + 2
R_SEV = Qt.ItemDataRole.UserRole + 3
R_KIND = Qt.ItemDataRole.UserRole + 4
R_CURATED = Qt.ItemDataRole.UserRole + 5
R_TOOL = Qt.ItemDataRole.UserRole + 6
COLUMN_WIDTH = 236
CARD_HEIGHT = 58


class BrickDelegate(QStyledItemDelegate):
    """Dessine une brique comme une carte Material : nom, sous-titre, état."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        line = option.fontMetrics.height()
        return QSize(theme.px(COLUMN_WIDTH) - 24, max(CARD_HEIGHT, 2 * line + 26))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        pal = theme.current()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 3, -2, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)

        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        fill = theme.qcolor(pal.background)
        if hovered and not selected:
            fill = theme.qcolor(pal.primary, 22)
        if selected:
            fill = theme.qcolor(pal.primary, 34)
        painter.fillPath(path, fill)
        border = theme.qcolor(pal.primary) if (selected or focused) else theme.qcolor(pal.border)
        painter.setPen(QPen(border, 2 if selected else 1))
        painter.drawPath(path)

        sev = index.data(R_SEV) or ""
        if sev:
            bar = QPainterPath()
            bar.addRoundedRect(rect.adjusted(0, 0, -(rect.width() - 5), 0), 3, 3)
            painter.fillPath(bar, theme.qcolor(pal.severity(sev)))

        curated = bool(index.data(R_CURATED))
        kind = index.data(R_KIND) or "tool"
        ic = icon(KIND_ICONS.get(kind, "mdi6.puzzle"), pal.primary if curated else pal.text_muted)
        ic.paint(painter, QRect(rect.left() + 12, rect.top() + 10, 18, 18))

        text_left = rect.left() + 38
        right_pad = 28 if sev else 10
        name_font = QFont(option.font)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(theme.qcolor(pal.text))
        line = painter.fontMetrics().height()
        name_rect = QRect(text_left, rect.top() + 6, rect.right() - text_left - right_pad, line + 2)
        name = painter.fontMetrics().elidedText(index.data(R_NAME) or "", Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        sub_font = QFont(option.font)
        if option.font.pixelSize() > 0:   # taille donnée en pixels par la feuille de style
            sub_font.setPixelSize(max(10, round(option.font.pixelSize() * 0.85)))
        else:
            sub_font.setPointSizeF(max(7.5, option.font.pointSizeF() - 1.5))
        painter.setFont(sub_font)
        painter.setPen(theme.qcolor(pal.text_muted))
        sub_rect = QRect(text_left, name_rect.bottom() + 3, rect.right() - text_left - 10, painter.fontMetrics().height() + 2)
        sub = painter.fontMetrics().elidedText(index.data(R_SUB) or "", Qt.TextElideMode.ElideRight, sub_rect.width())
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub)

        if sev:
            icon(SEVERITY_ICONS[sev], pal.severity(sev)).paint(painter, QRect(rect.right() - 24, rect.top() + 9, 18, 18))
        painter.restore()


class StageList(QListWidget):
    toolDropped = Signal(str, str, int)      # stage, tool_id, index
    brickMoved = Signal(str, str, int)       # uid, stage, index
    deleteRequested = Signal(str)
    shiftRequested = Signal(str, int)        # uid, delta d'étape
    dropRefused = Signal(str, str)           # tool_id, stage
    dragStarted = Signal(str)                # tool_id
    dragFinished = Signal()

    def __init__(self, stage: str, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.stage = stage
        self.drop_state = ""                 # "", "ok" ou "no" pendant un glisser
        self.can_place: Callable[[str, str], bool] = lambda tool, stage: True
        self.setObjectName("stageList")
        self.setItemDelegate(BrickDelegate(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setSpacing(1)
        self.setAccessibleName(f"Étape {label}")
        self.setAccessibleDescription("Suppr retire la brique ; Alt+gauche ou droite la change d'étape, "
                                      "Alt+haut ou bas la déplace dans l'étape.")

    # ----------------------------------------------------------- glisser-déposer
    def mimeTypes(self):  # noqa: N802
        return [MIME_TOOL, MIME_BRICK]

    def mimeData(self, items):  # noqa: N802
        data = QMimeData()
        if items:
            data.setData(MIME_BRICK, f"{items[0].data(R_UID)}|{items[0].data(R_TOOL)}".encode())
        return data

    def startDrag(self, actions):  # noqa: N802
        item = self.currentItem()
        self.dragStarted.emit(item.data(R_TOOL) if item else "")
        try:
            super().startDrag(actions)
        finally:
            self.dragFinished.emit()

    @staticmethod
    def payload(md: QMimeData) -> tuple[str | None, str | None]:
        """(uid, tool_id) transportés par un glisser ; uid vaut None depuis la palette."""
        if md.hasFormat(MIME_TOOL):
            return None, bytes(md.data(MIME_TOOL)).decode()
        if md.hasFormat(MIME_BRICK):
            uid, _, tool = bytes(md.data(MIME_BRICK)).decode().partition("|")
            return uid, tool
        return None, None

    def _accepts(self, event) -> bool:
        _, tool = self.payload(event.mimeData())
        return tool is not None and self.can_place(tool, self.stage)

    def dragEnterEvent(self, event):  # noqa: N802
        _, tool = self.payload(event.mimeData())
        if tool is None:
            event.ignore()
        elif not self.can_place(tool, self.stage):
            self.dropRefused.emit(tool, self.stage)
            event.ignore()  # le curseur « interdit » s'affiche
        else:
            event.setDropAction(Qt.DropAction.CopyAction if event.mimeData().hasFormat(MIME_TOOL) else Qt.DropAction.MoveAction)
            event.accept()

    def dragMoveEvent(self, event):  # noqa: N802
        if self._accepts(event):
            super().dragMoveEvent(event)
            event.setDropAction(Qt.DropAction.CopyAction if event.mimeData().hasFormat(MIME_TOOL) else Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def _drop_row(self, event) -> int:
        idx = self.indexAt(event.position().toPoint())
        if not idx.isValid():
            return self.count()
        rect = self.visualRect(idx)
        return idx.row() + (1 if event.position().y() > rect.center().y() else 0)

    def dropEvent(self, event):  # noqa: N802
        uid, tool = self.payload(event.mimeData())
        if tool is None or not self.can_place(tool, self.stage):
            event.ignore()
            return
        row = self._drop_row(event)
        stage = self.stage
        # Le modèle est modifié après la fin du glisser : la liste source est encore
        # dans sa boucle de glisser-déposer et ne doit pas être reconstruite ici.
        if uid is None:
            QTimer.singleShot(0, lambda: self.toolDropped.emit(stage, tool, row))
        else:
            QTimer.singleShot(0, lambda: self.brickMoved.emit(uid, stage, row))
        event.setDropAction(Qt.DropAction.CopyAction)  # le modèle se charge du déplacement
        event.accept()

    # ----------------------------------------------------------------- clavier
    def keyPressEvent(self, event):  # noqa: N802
        item = self.currentItem()
        if item is not None:
            uid = item.data(R_UID)
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.deleteRequested.emit(uid)
                return
            if event.modifiers() & Qt.KeyboardModifier.AltModifier and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                self.shiftRequested.emit(uid, -1 if event.key() == Qt.Key.Key_Left else 1)
                return
            # Alt+haut / Alt+bas : l'équivalent clavier du glisser dans la colonne (WCAG 2.5.7)
            row = self.row(item)
            if event.modifiers() & Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_Up and row > 0:
                self.brickMoved.emit(uid, self.stage, row - 1)
                return
            if event.modifiers() & Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_Down \
                    and row < self.count() - 1:
                self.brickMoved.emit(uid, self.stage, row + 2)  # index avant retrait, comme un dépôt
                return
        super().keyPressEvent(event)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        pal = theme.current()
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = self.viewport().rect()
        if self.drop_state == "no":
            painter.fillRect(full, theme.qcolor(pal.background, 200))
            painter.setPen(theme.qcolor(pal.text_muted))
            painter.drawText(full.adjusted(8, 8, -8, -8), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             "Étape non compatible")
            return
        if self.count() == 0 or self.drop_state == "ok":
            r = full.adjusted(4, 4, -4, -4)
            if self.count():
                top = self.visualItemRect(self.item(self.count() - 1)).bottom() + 6
                r.setTop(min(top, r.bottom() - 40))
            r.setHeight(min(r.height(), 72))
            ok = self.drop_state == "ok"
            painter.setPen(QPen(theme.qcolor(pal.primary if ok else pal.border), 2 if ok else 1.5, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(r, 8, 8)
            painter.setPen(theme.qcolor(pal.primary if ok else pal.text_muted))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "Déposer ici" if ok else "Glissez une brique ici")


class StageColumn(QFrame):
    def __init__(self, stage: str, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("stageCard")
        self.setFixedWidth(theme.px(COLUMN_WIDTH))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(DecorativeIcon(STAGE_ICONS[stage]))
        title = QLabel(label)
        title.setObjectName("stageTitle")
        head.addWidget(title, 1)
        self.count = QLabel("0")
        self.count.setObjectName("stageCount")
        head.addWidget(self.count)
        lay.addLayout(head)
        self.list = StageList(stage, label)
        lay.addWidget(self.list, 1)

    def set_drop_state(self, state: str) -> None:
        self.setProperty("dropState", state)
        self.list.drop_state = state
        for w in (self, *self.findChildren(QLabel)):
            w.style().unpolish(w)
            w.style().polish(w)
        self.list.viewport().update()


class PipelineCanvas(QScrollArea):
    selectionChanged = Signal(str)
    toolDropped = Signal(str, str, int)
    brickMoved = Signal(str, str, int)
    deleteRequested = Signal(str)
    shiftRequested = Signal(str, int)
    dropRefused = Signal(str, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("canvasScroll")
        self.setAccessibleName("Pipeline")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        inner = QWidget()
        inner.setObjectName("canvasInner")
        self.row = QHBoxLayout(inner)
        self.row.setContentsMargins(16, 16, 16, 16)
        self.row.setSpacing(12)
        self.columns: dict[str, StageColumn] = {}
        for sid, label in STAGES:
            col = StageColumn(sid, label)
            self.columns[sid] = col
            self.row.addWidget(col)
            lst = col.list
            lst.toolDropped.connect(self.toolDropped)
            lst.brickMoved.connect(self.brickMoved)
            lst.deleteRequested.connect(self.deleteRequested)
            lst.shiftRequested.connect(self.shiftRequested)
            lst.dropRefused.connect(self.dropRefused)
            lst.dragStarted.connect(self.highlight)
            lst.dragFinished.connect(self.clear_highlight)
            lst.itemSelectionChanged.connect(lambda l=lst: self._selection(l))
        self.row.addStretch(1)
        self.setWidget(inner)
        self._updating = False
        self._can_place: Callable[[str, str], bool] = lambda tool, stage: True

    # ------------------------------------------------------------ compatibilité
    def set_placement_check(self, fn: Callable[[str, str], bool]) -> None:
        self._can_place = fn
        for col in self.columns.values():
            col.list.can_place = fn

    def highlight(self, tool_id: str) -> None:
        """Pendant un glisser : colonnes compatibles en évidence, les autres grisées."""
        if not tool_id:
            return
        for sid, col in self.columns.items():
            col.set_drop_state("ok" if self._can_place(tool_id, sid) else "no")

    def clear_highlight(self) -> None:
        for col in self.columns.values():
            col.set_drop_state("")

    def _selection(self, source: StageList) -> None:
        if self._updating:
            return
        items = source.selectedItems()
        if not items:
            return
        self._updating = True
        for col in self.columns.values():
            if col.list is not source:
                col.list.clearSelection()
        self._updating = False
        self.selectionChanged.emit(items[0].data(R_UID))

    def rebuild(self, project: Project, catalog: Catalog, severity: dict[str, str], selected: str | None) -> None:
        from ..datainfo import infos
        self._updating = True
        data = infos(project, catalog)
        for sid, col in self.columns.items():
            lst = col.list
            lst.clear()
            bricks = project.stages.get(sid, [])
            col.count.setText(str(len(bricks)))
            col.count.setAccessibleName(f"{len(bricks)} brique" + ("s" if len(bricks) > 1 else ""))
            for b in bricks:
                t = catalog.get(b.tool)
                item = QListWidgetItem()
                name = t.name if t else b.tool
                item.setData(R_UID, b.uid)
                item.setData(R_TOOL, b.tool)
                item.setData(R_NAME, name)
                info = data.get(b.tool)
                sub = (f"{info.badge} · {info.db.url_var}" if info else self._subtitle(t) if t else "Fiche introuvable")
                if t and t.curated and t.support_level != "supported":
                    sub = f"{SUPPORT[t.support_level]} · {sub}" if sub else SUPPORT[t.support_level]
                item.setData(R_SUB, sub)
                item.setData(R_SEV, severity.get(b.uid, ""))
                item.setData(R_KIND, t.kind if t else "tool")
                item.setData(R_CURATED, bool(t and t.curated))
                sev = severity.get(b.uid)
                level = f", {SUPPORT[t.support_level].lower()}" if t and t.curated and t.support_level != "supported" else ""
                item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{name}{level}{', ' + sev if sev else ''}")
                item.setToolTip((f"{info.where}\n{info.connection}\n{info.secret}" if info else "")
                                or (t.description if t else ""))
                lst.addItem(item)
                if b.uid == selected:
                    lst.setCurrentItem(item)
        self._updating = False

    @staticmethod
    def _subtitle(t) -> str:
        if not t.curated:
            return "Landscape · non vérifiée"
        if t.kind == "provider":
            return "Fournisseur cloud"
        parts = []
        if t.provider:
            parts.append(t.provider.upper() if len(t.provider) <= 3 else t.provider.capitalize())
        if t.roles:
            parts.append(", ".join(t.roles[:2]))
        return " · ".join(parts)

    def rescale(self) -> None:
        """Largeur des colonnes et hauteur des cartes après un changement de taille du texte."""
        for col in self.columns.values():
            col.setFixedWidth(theme.px(COLUMN_WIDTH))
            col.list.doItemsLayout()

    def select(self, uid: str) -> None:
        for col in self.columns.values():
            for i in range(col.list.count()):
                item = col.list.item(i)
                if item.data(R_UID) == uid:
                    col.list.setCurrentItem(item)
                    col.list.setFocus()
                    self.ensureWidgetVisible(col)
                    return
