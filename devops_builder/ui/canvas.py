"""Canevas du pipeline : une carte par étape, des briques glissables."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QModelIndex, QRect, QSize, Qt, Signal
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
from ..model import STAGES, Project
from . import theme
from .palette import MIME_TOOL
from .widgets import KIND_ICONS, SEVERITY_ICONS, STAGE_ICONS, icon

MIME_BRICK = "application/x-devops-brick"
R_UID = Qt.ItemDataRole.UserRole
R_NAME = Qt.ItemDataRole.UserRole + 1
R_SUB = Qt.ItemDataRole.UserRole + 2
R_SEV = Qt.ItemDataRole.UserRole + 3
R_KIND = Qt.ItemDataRole.UserRole + 4
R_CURATED = Qt.ItemDataRole.UserRole + 5
COLUMN_WIDTH = 236
CARD_HEIGHT = 58


class BrickDelegate(QStyledItemDelegate):
    """Dessine une brique comme une carte Material : nom, sous-titre, état."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(COLUMN_WIDTH - 24, CARD_HEIGHT)

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
        name_rect = QRect(text_left, rect.top() + 7, rect.right() - text_left - right_pad, 20)
        name = painter.fontMetrics().elidedText(index.data(R_NAME) or "", Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        sub_font = QFont(option.font)
        sub_font.setPointSizeF(max(7.5, option.font.pointSizeF() - 1.5))
        painter.setFont(sub_font)
        painter.setPen(theme.qcolor(pal.text_muted))
        sub_rect = QRect(text_left, rect.top() + 28, rect.right() - text_left - 10, 18)
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

    def __init__(self, stage: str, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.stage = stage
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
        self.setAccessibleDescription("Suppr retire la brique ; Alt+flèches la déplace d'étape.")

    # ----------------------------------------------------------- glisser-déposer
    def mimeTypes(self):  # noqa: N802
        return [MIME_TOOL, MIME_BRICK]

    def mimeData(self, items):  # noqa: N802
        data = QMimeData()
        if items:
            data.setData(MIME_BRICK, items[0].data(R_UID).encode())
        return data

    def _accepts(self, event) -> bool:
        md = event.mimeData()
        return md.hasFormat(MIME_TOOL) or md.hasFormat(MIME_BRICK)

    def dragEnterEvent(self, event):  # noqa: N802
        if self._accepts(event):
            event.setDropAction(Qt.DropAction.CopyAction if event.mimeData().hasFormat(MIME_TOOL) else Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

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
        md = event.mimeData()
        row = self._drop_row(event)
        if md.hasFormat(MIME_TOOL):
            self.toolDropped.emit(self.stage, bytes(md.data(MIME_TOOL)).decode(), row)
        elif md.hasFormat(MIME_BRICK):
            self.brickMoved.emit(bytes(md.data(MIME_BRICK)).decode(), self.stage, row)
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
        super().keyPressEvent(event)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            pal = theme.current()
            painter.setPen(QPen(theme.qcolor(pal.border), 1.5, Qt.PenStyle.DashLine))
            r = self.viewport().rect().adjusted(4, 4, -4, -4)
            r.setHeight(min(r.height(), 72))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawRoundedRect(r, 8, 8)
            painter.setPen(theme.qcolor(pal.text_muted))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "Glissez une brique ici")


class StageColumn(QFrame):
    def __init__(self, stage: str, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("stageCard")
        self.setFixedWidth(COLUMN_WIDTH)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icon(STAGE_ICONS[stage], theme.current().primary).pixmap(20, 20))
        head.addWidget(ic)
        title = QLabel(label)
        title.setObjectName("stageTitle")
        head.addWidget(title, 1)
        self.count = QLabel("0")
        self.count.setObjectName("stageCount")
        head.addWidget(self.count)
        lay.addLayout(head)
        self.list = StageList(stage, label)
        lay.addWidget(self.list, 1)


class PipelineCanvas(QScrollArea):
    selectionChanged = Signal(str)
    toolDropped = Signal(str, str, int)
    brickMoved = Signal(str, str, int)
    deleteRequested = Signal(str)
    shiftRequested = Signal(str, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("canvasScroll")
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
            lst.itemSelectionChanged.connect(lambda l=lst: self._selection(l))
        self.row.addStretch(1)
        self.setWidget(inner)
        self._updating = False

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
        self._updating = True
        for sid, col in self.columns.items():
            lst = col.list
            lst.clear()
            bricks = project.stages.get(sid, [])
            col.count.setText(str(len(bricks)))
            for b in bricks:
                t = catalog.get(b.tool)
                item = QListWidgetItem()
                name = t.name if t else b.tool
                item.setData(R_UID, b.uid)
                item.setData(R_NAME, name)
                item.setData(R_SUB, self._subtitle(t) if t else "Fiche introuvable")
                item.setData(R_SEV, severity.get(b.uid, ""))
                item.setData(R_KIND, t.kind if t else "tool")
                item.setData(R_CURATED, bool(t and t.curated))
                sev = severity.get(b.uid)
                item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{name}{', ' + sev if sev else ''}")
                item.setToolTip(t.description if t else "")
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

    def select(self, uid: str) -> None:
        for col in self.columns.values():
            for i in range(col.list.count()):
                item = col.list.item(i)
                if item.data(R_UID) == uid:
                    col.list.setCurrentItem(item)
                    col.list.setFocus()
                    self.ensureWidgetVisible(col)
                    return
