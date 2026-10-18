# SPDX-License-Identifier: Apache-2.0
"""Vue « Réseau » : le schéma d'un environnement en 2D ou en 3D isométrique, avec les erreurs sur les composants.

Le dessin (`NetworkView`) est une aide visuelle : tout ce qu'il montre existe aussi dans la liste « Composants et
constats » à droite, que les lecteurs d'écran et le clavier atteignent. Une erreur n'est jamais portée par la
couleur seule : la pastille change de forme (disque barré, triangle, disque) et le constat est écrit.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSettings, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..catalog import Catalog
from ..model import Project, Severity
from ..network import LAYER_LABELS, LAYERS, NetEdge, NetGraph, NetNode, build_graph
from ..rules import Action, RuleEngine
from . import theme
from .a11y import announce
from .widgets import SEVERITY_ICONS, clear_layout, icon, muted, plain, section_title

SEVERITY_SYMBOL = {Severity.BLOCKING: "×", Severity.WARNING: "!", Severity.INFO: "i"}
SEVERITY_WORD = {Severity.BLOCKING: "erreur bloquante", Severity.WARNING: "avertissement", Severity.INFO: "information"}


def _mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t), round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t))


def count_text(count: int, word: str) -> str:
    return f"{count} {word}" + ("s" if count > 1 and not word.endswith("s") else "")


class _WrapDelegate(QStyledItemDelegate):
    """Lignes de la liste : hauteur d'après le texte replié, icône et retrait déduits de la largeur."""

    def sizeHint(self, option, index):  # noqa: N802
        size = super().sizeHint(option, index)
        width = self.parent().viewport().width() - (110 if index.parent().isValid() else 70)
        text = index.data() or ""
        if width > 60 and text:
            rect = option.fontMetrics.boundingRect(QRect(0, 0, width, 100000), Qt.TextFlag.TextWordWrap, text)
            size.setHeight(max(size.height(), rect.height() + 12))
        return size


class NetworkView(QWidget):
    """Dessine un `NetGraph` à plat (2D) ou en plans isométriques empilés (3D) ; clic ou flèches pour choisir."""

    nodeSelected = Signal(str)
    nodeActivated = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        self._size = QSize(480, 320)
        self.zoom = 1.25   # taille du dessin : 1,0 à 2,0 ; les textes et les espaces suivent
        super().__init__(parent)
        self.graph: NetGraph | None = None
        self.mode = "2d"
        self.selected: str | None = None
        self._hits: list[tuple[str, QPainterPath]] = []
        self._pills: dict[str, QRectF] = {}
        self._anchors: dict[str, QPointF] = {}
        self._plates: list[tuple[str, QPolygonF | QRectF]] = []
        self._boxes: list[tuple[str, list[QPolygonF]]] = []
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Schéma réseau")
        self.setAccessibleDescription("Flèches : passer d'un composant au suivant ; Entrée : voir sa brique. "
                                      "La liste Composants et constats donne la même information en texte.")

    # ------------------------------------------------------------------ données
    def set_graph(self, graph: NetGraph, selected: str | None = None) -> None:
        self.graph = graph
        self.selected = selected if selected and graph.node(selected) else None
        self._relayout()

    def _px(self, value: float) -> int:
        return round(theme.px(value) * self.zoom)

    def set_zoom(self, zoom: float) -> None:
        self.zoom = zoom
        self._relayout()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._relayout()

    def select(self, node_id: str | None, emit: bool = True) -> None:
        if node_id == self.selected:
            return
        self.selected = node_id
        self.update()
        if emit and node_id:
            self.nodeSelected.emit(node_id)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self._size

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self._size

    # ------------------------------------------------------------------ géométrie
    def _metrics(self) -> tuple[QFont, QFont]:
        base = max(8.0, self.font().pointSizeF()) * self.zoom
        label = QFont(self.font())
        label.setBold(True)
        label.setPointSizeF(base * 1.15)
        small = QFont(self.font())
        small.setPointSizeF(base * 0.95)
        return label, small

    def _relayout(self) -> None:
        self._hits, self._pills, self._anchors, self._plates, self._boxes = [], {}, {}, [], []
        self._size = QSize(self._px(480), self._px(320))
        if self.graph is None or not self.graph.nodes:
            self.updateGeometry()
            self.update()
            return
        (self._layout_3d if self.mode == "3d" else self._layout_2d)()
        self.updateGeometry()
        self.resize(self._size)
        self.update()

    def _pill_size(self, node: NetNode) -> QSizeF:
        label, small = self._metrics()
        w = max(QFontMetricsF(label).horizontalAdvance(node.label), QFontMetricsF(small).horizontalAdvance(node.detail))
        return QSizeF(max(self._px(150), w + self._px(44)), QFontMetricsF(label).height() + QFontMetricsF(small).height()
                      + self._px(22))

    def _layout_2d(self) -> None:
        g = self.graph
        layers = [(layer, g.layer(layer)) for layer in LAYERS if g.layer(layer)]
        sizes = {n.id: self._pill_size(n) for n in g.nodes}
        gap, margin, band_pad = self._px(56), self._px(32), self._px(18)
        left = self._px(40)
        widths = [sum(sizes[n.id].width() for n in nodes) + gap * (len(nodes) - 1) for _, nodes in layers]
        total = max(widths) + left + 2 * margin
        y = margin
        for (layer, nodes), width in zip(layers, widths, strict=True):
            height = max(sizes[n.id].height() for n in nodes) + 2 * band_pad
            band = QRectF(margin, y, total - 2 * margin, height + self._px(34))
            self._plates.append((layer, band))
            x = left + margin + (total - left - 2 * margin - width) / 2
            for n in nodes:
                size = sizes[n.id]
                rect = QRectF(x, y + self._px(34) + band_pad, size.width(), size.height())
                self._pills[n.id] = rect
                path = QPainterPath()
                path.addRoundedRect(rect.adjusted(-4, -4, 4, 4), 10, 10)
                self._hits.append((n.id, path))
                x += size.width() + gap
            y += band.height() + self._px(64)   # l'espace entre deux plans porte les flèches
        self._size = QSize(round(total), round(y - self._px(64) + margin))

    def _layout_3d(self) -> None:
        g = self.graph
        layers = [(layer, g.layer(layer)) for layer in LAYERS if g.layer(layer)]
        k = theme.scale() * 0.7 * self.zoom
        col, depth, zgap = 215.0, 200.0, 270.0
        most = max(len(nodes) for _, nodes in layers)
        pw = most * col + 90

        def iso(x: float, y: float, z: float) -> QPointF:
            return QPointF((x - y) * 0.866 * k, (x + y) * 0.5 * k - z * k)

        raw: list[tuple[str, list[QPointF], float]] = []
        boxes: list[tuple[str, list[list[QPointF]]]] = []
        anchors: dict[str, QPointF] = {}
        for i, (layer, nodes) in enumerate(layers):
            z = (len(layers) - 1 - i) * zgap
            raw.append((layer, [iso(0, 0, z), iso(pw, 0, z), iso(pw, depth, z), iso(0, depth, z)], z))
            for j, n in enumerate(nodes):
                cx = 45 + col * (j + 0.5) + (most - len(nodes)) * col / 2
                x0, x1, y0, y1, h = cx - 52, cx + 52, depth / 2 - 34, depth / 2 + 34, 28
                top = [iso(x0, y0, z + h), iso(x1, y0, z + h), iso(x1, y1, z + h), iso(x0, y1, z + h)]
                left = [iso(x0, y1, z + h), iso(x1, y1, z + h), iso(x1, y1, z), iso(x0, y1, z)]
                right = [iso(x1, y0, z + h), iso(x1, y1, z + h), iso(x1, y1, z), iso(x1, y0, z)]
                boxes.append((n.id, [top, left, right]))
                anchors[n.id] = iso(cx, depth / 2, z + h)
        points = [p for _, poly, _ in raw for p in poly] + [p for _, faces in boxes for f in faces for p in f]
        margin = self._px(40)
        min_x = min(p.x() for p in points) - margin - self._px(190)   # place du titre des plans, à gauche
        min_y = min(p.y() for p in points) - margin - self._px(20)
        max_x = max(p.x() for p in points) + margin
        max_y = max(p.y() for p in points) + margin
        shift = QPointF(-min_x, -min_y)
        self._size = QSize(round(max_x - min_x), round(max_y - min_y))
        for layer, poly, _ in raw:
            self._plates.append((layer, QPolygonF([p + shift for p in poly])))
        for node_id, faces in boxes:
            shifted = [QPolygonF([p + shift for p in f]) for f in faces]
            self._boxes.append((node_id, shifted))
        for node_id, point in anchors.items():
            self._anchors[node_id] = point + shift
        for node in g.nodes:
            size = self._pill_size(node)
            centre = self._anchors[node.id] + QPointF(0, -size.height() / 2 - self._px(4))
            rect = QRectF(centre.x() - size.width() / 2, centre.y() - size.height() / 2, size.width(), size.height())
            self._pills[node.id] = rect
            path = QPainterPath()
            path.addRoundedRect(rect.adjusted(-4, -4, 4, 4), 10, 10)
            for _id, faces in self._boxes:
                if _id == node.id:
                    for f in faces:
                        path.addPolygon(f)
            self._hits.append((node.id, path.simplified()))

    # ------------------------------------------------------------------ dessin
    def paintEvent(self, event) -> None:  # noqa: N802
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(p.background))
        painter.translate(self._offset())
        g = self.graph
        if g is None or not g.nodes:
            painter.setPen(QColor(p.text_muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Aucun composant à afficher pour cet environnement.")
            painter.end()
            return
        label_font, small_font = self._metrics()
        self._draw_plates(painter, p, small_font)
        if self.mode == "3d":
            self._draw_boxes(painter, p)
        self._spread_ends()
        for edge in g.edges:
            self._draw_edge(painter, p, edge, small_font)
        for node in g.nodes:
            self._draw_pill(painter, p, node, label_font, small_font)
        painter.end()

    def _draw_plates(self, painter: QPainter, p, small: QFont) -> None:
        small = QFont(small)
        small.setBold(True)
        painter.setFont(small)
        for layer, shape in self._plates:
            fill = _mix(p.surface, p.background, 0.0 if self.mode == "2d" else 0.15)
            painter.setPen(QPen(QColor(p.border), 1))
            painter.setBrush(fill)
            if isinstance(shape, QRectF):
                painter.drawRoundedRect(shape, 10, 10)
                painter.setPen(QColor(p.text_muted))
                painter.drawText(QPointF(shape.left() + self._px(14), shape.top() + self._px(19)), LAYER_LABELS[layer])
            else:
                painter.drawPolygon(shape)
                painter.setPen(QColor(p.text_muted))
                corner = shape[3]   # coin gauche du plan
                painter.drawText(QPointF(corner.x() - self._px(8) - QFontMetricsF(small).horizontalAdvance(LAYER_LABELS[layer]),
                                         corner.y() + self._px(16)), LAYER_LABELS[layer])

    def _draw_boxes(self, painter: QPainter, p) -> None:
        top_color = _mix(p.surface, p.primary, 0.12)
        for _node_id, (top, left, right) in sorted(self._boxes, key=lambda b: -b[1][0][0].y()):
            painter.setPen(QPen(QColor(p.border), 1))
            for face, shade in ((left, 0.35), (right, 0.55), (top, 0.0)):
                painter.setBrush(_mix(top_color.name(), p.text, shade * 0.35))
                painter.drawPolygon(face)

    def _spread_ends(self) -> None:
        """Plusieurs flèches sur le même bord d'un composant s'y répartissent au lieu de se superposer."""
        ends: dict[tuple[str, str], list[tuple[int, int, float]]] = {}
        for i, edge in enumerate(self.graph.edges):
            a, b = self._pills.get(edge.src), self._pills.get(edge.dst)
            if a is None or b is None or (self.mode != "3d" and abs(a.center().y() - b.center().y()) <= 2):
                continue
            a_up = a.center().y() < b.center().y()
            ends.setdefault((edge.src, "bottom" if a_up else "top"), []).append((i, 0, b.center().x()))
            ends.setdefault((edge.dst, "top" if a_up else "bottom"), []).append((i, 1, a.center().x()))
        self._slots: dict[tuple[int, int], float] = {}
        for items in ends.values():
            items.sort(key=lambda t: t[2])   # de gauche à droite, d'après la position de l'autre extrémité
            for rank, (i, end, _x) in enumerate(items):
                self._slots[(i, end)] = (rank + 1) / (len(items) + 1)

    def _edge_points(self, edge: NetEdge) -> tuple[QPointF, QPointF] | None:
        a, b = self._pills.get(edge.src), self._pills.get(edge.dst)
        if a is None or b is None:
            return None
        if self.mode == "3d" or abs(a.center().y() - b.center().y()) > 2:
            i = self.graph.edges.index(edge)
            upper, lower = (a, b) if a.center().y() < b.center().y() else (b, a)
            start = QPointF(a.left() + a.width() * self._slots.get((i, 0), 0.5), a.bottom() if a is upper else a.top())
            end = QPointF(b.left() + b.width() * self._slots.get((i, 1), 0.5), b.top() if b is lower else b.bottom())
            return start, end
        left, right = (a, b) if a.center().x() < b.center().x() else (b, a)
        return (QPointF(a.right(), a.center().y()), QPointF(b.left(), b.center().y())) if a is left else \
            (QPointF(a.left(), a.center().y()), QPointF(b.right(), b.center().y()))

    def _draw_edge(self, painter: QPainter, p, edge: NetEdge, small: QFont) -> None:
        pts = self._edge_points(edge)
        if pts is None:
            return
        start, end = pts
        risky = edge.public and not edge.secure
        color = QColor(p.warning if risky else (p.primary if edge.public else p.text_muted))
        pen = QPen(color, (2.6 if edge.public else 2.0) * min(self.zoom, 1.6))
        if risky:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(start)
        mid_y = (start.y() + end.y()) / 2
        path.cubicTo(QPointF(start.x(), mid_y), QPointF(end.x(), mid_y), end)
        painter.drawPath(path)
        angle = math.atan2(end.y() - path.pointAtPercent(0.97).y(), end.x() - path.pointAtPercent(0.97).x())
        a = 12 * self.zoom
        head = QPolygonF([end, QPointF(end.x() - a * math.cos(angle - 0.4), end.y() - a * math.sin(angle - 0.4)),
                          QPointF(end.x() - a * math.cos(angle + 0.4), end.y() - a * math.sin(angle + 0.4))])
        painter.setBrush(color)
        painter.drawPolygon(head)
        if edge.label:
            painter.setFont(small)
            mid = path.pointAtPercent(0.5)
            fm = QFontMetricsF(small)
            box = QRectF(mid.x() - fm.horizontalAdvance(edge.label) / 2 - 8, mid.y() - fm.height() / 2 - 3,
                         fm.horizontalAdvance(edge.label) + 16, fm.height() + 6)
            painter.setPen(QPen(color, 1))
            painter.setBrush(QColor(p.surface))
            painter.drawRoundedRect(box, 8, 8)
            painter.setPen(QColor(p.text))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, edge.label)

    def _draw_pill(self, painter: QPainter, p, node: NetNode, label_font: QFont, small_font: QFont) -> None:
        rect = self._pills[node.id]
        worst = self.graph.worst(node.id)
        selected = node.id == self.selected
        border = QColor(p.severity(worst.value)) if worst else QColor(p.border)
        painter.setPen(QPen(QColor(p.primary) if selected else border, 3.5 if selected else (2.5 if worst else 1.2)))
        painter.setBrush(QColor(p.surface))
        painter.drawRoundedRect(rect, 9, 9)
        if selected and self.hasFocus():
            painter.setPen(QPen(QColor(p.primary), 1.5, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-5, -5, 5, 5), 12, 12)
        painter.setPen(QColor(p.text))
        painter.setFont(label_font)
        lm = QFontMetricsF(label_font)
        painter.drawText(QPointF(rect.left() + self._px(14), rect.top() + self._px(10) + lm.ascent()), node.label)
        painter.setPen(QColor(p.text_muted))
        painter.setFont(small_font)
        painter.drawText(QPointF(rect.left() + self._px(14), rect.top() + self._px(10) + lm.height() + QFontMetricsF(small_font).ascent()),
                         node.detail)
        if worst:
            self._draw_badge(painter, p, rect, worst, len(self.graph.findings_of(node.id)))

    def _draw_badge(self, painter: QPainter, p, rect: QRectF, severity: Severity, count: int) -> None:
        d = self._px(26)
        box = QRectF(rect.right() - d * 0.6, rect.top() - d * 0.45, d, d)
        color = QColor(p.severity(severity.value))
        painter.setPen(QPen(QColor(p.surface), 1.5))
        painter.setBrush(color)
        if severity is Severity.WARNING:
            tri = QPolygonF([QPointF(box.center().x(), box.top() - 1), QPointF(box.right() + 2, box.bottom()),
                             QPointF(box.left() - 2, box.bottom())])
            painter.drawPolygon(tri)
        else:
            painter.drawEllipse(box)
        painter.setPen(QColor(p.background if p.dark else "#ffffff"))
        font = QFont(self.font())
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(box.adjusted(0, 3 if severity is Severity.WARNING else 0, 0, 0), Qt.AlignmentFlag.AlignCenter,
                         SEVERITY_SYMBOL[severity])
        if count > 1:
            painter.setPen(QColor(p.text))
            small = QFont(self.font())
            small.setPointSizeF(max(8.0, self.font().pointSizeF() * self.zoom))
            painter.setFont(small)
            painter.drawText(QPointF(box.right() + 4, box.center().y() + 4), f"×{count}")

    # ------------------------------------------------------------------ souris et clavier
    def _offset(self) -> QPointF:
        """Le dessin est centré quand la fenêtre est plus large que lui."""
        return QPointF(max(0, (self.width() - self._size.width()) / 2), 0)

    def _node_at(self, pos: QPointF) -> str | None:
        pos = pos - self._offset()
        for node_id, path in reversed(self._hits):
            if path.contains(pos):
                return node_id
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.setFocus()
        node = self._node_at(event.position())
        if node:
            self.select(node)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        node = self._node_at(event.position())
        if node:
            self.nodeActivated.emit(node)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        node = self._node_at(event.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if node else Qt.CursorShape.ArrowCursor)
        self.setToolTip(self.describe(node) if node else "")
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.graph is None or not self.graph.nodes:
            return super().keyPressEvent(event)
        ids = [n.id for n in self.graph.nodes]
        index = ids.index(self.selected) if self.selected in ids else -1
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.select(ids[(index + 1) % len(ids)])
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.select(ids[(index - 1) % len(ids)])
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.selected:
            self.nodeActivated.emit(self.selected)
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        if self.selected is None and self.graph and self.graph.nodes:
            self.select(self.graph.nodes[0].id)
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self.update()

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange) and self.graph is not None:
            self._relayout()
        super().changeEvent(event)

    def describe(self, node_id: str | None) -> str:
        node = self.graph.node(node_id) if self.graph and node_id else None
        if node is None:
            return ""
        found = self.graph.findings_of(node.id)
        text = f"{node.label} — {node.detail}"
        if node.ports:
            text += f" (ports {', '.join(node.ports)})"
        if found:
            text += " : " + " ; ".join(f"{SEVERITY_WORD[f.severity]} : {f.message}" for f in found)
        else:
            text += " : aucun constat"
        return text


class NetworkDialog(QDialog):
    def __init__(self, project: Project, catalog: Catalog, engine: RuleEngine, parent: QWidget | None = None,
                 apply_fix: Callable[[Action], Project] | None = None,
                 focus_brick: Callable[[str], None] | None = None):
        super().__init__(parent)
        self.project, self.catalog, self.engine = project, catalog, engine
        self.apply_fix, self.focus_brick = apply_fix, focus_brick
        self.graph: NetGraph | None = None
        self.setWindowTitle("Réseau")
        self.resize(1400, 880)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.env = QComboBox()
        self.env.setAccessibleName("Environnement")
        for e in project.environments:
            self.env.addItem(e.display, e.id)
        if project.environments:
            self.env.setCurrentIndex(len(project.environments) - 1)   # la production d'abord
        self.env.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.env)
        self.mode = QComboBox()
        self.mode.setAccessibleName("Affichage du schéma")
        self.mode.addItem(icon("mdi6.vector-square"), "Plan 2D", "2d")
        self.mode.addItem(icon("mdi6.cube-outline"), "Isométrique 3D", "3d")
        saved = QSettings("DevOpsBuilder", "DevOpsBuilder").value("network/view", "2d")
        self.mode.setCurrentIndex(1 if saved == "3d" else 0)
        self.mode.currentIndexChanged.connect(lambda _: self._set_mode(self.mode.currentData()))
        top.addWidget(self.mode)
        self.size_combo = QComboBox()
        self.size_combo.setAccessibleName("Taille du schéma")
        for label, value in (("Taille 100 %", 1.0), ("Taille 125 %", 1.25), ("Taille 150 %", 1.5), ("Taille 200 %", 2.0)):
            self.size_combo.addItem(label, value)
        saved_zoom = float(QSettings("DevOpsBuilder", "DevOpsBuilder").value("network/zoom", 1.25))
        self.size_combo.setCurrentIndex(max(0, self.size_combo.findData(saved_zoom)))
        self.size_combo.currentIndexChanged.connect(self._set_zoom)
        top.addWidget(self.size_combo)
        top.addStretch(1)
        self.save_btn = QPushButton(icon("mdi6.image-outline"), "Enregistrer l'image…")
        self.save_btn.clicked.connect(self.save_image)
        top.addWidget(self.save_btn)
        lay.addLayout(top)
        self.legend = muted("Trait plein : flux interne ou chiffré · trait pointillé : flux public sans TLS · "
                            "pastille ✕ erreur bloquante, ▲ avertissement, ● information.")
        self.legend.setWordWrap(True)
        lay.addWidget(self.legend)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.view = NetworkView()
        self.view.nodeSelected.connect(self._node_selected)
        self.view.nodeActivated.connect(self._open_brick)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.view)
        scroll.setAccessibleName("Schéma réseau (zone de défilement)")
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        split.addWidget(scroll)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(section_title("Composants et constats"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName("Composants et constats")
        self.tree.setWordWrap(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setItemDelegate(_WrapDelegate(self.tree))
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.currentItemChanged.connect(self._item_changed)
        sl.addWidget(self.tree, 1)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.detail.setAccessibleName("Détail du constat")
        sl.addWidget(self.detail)
        self.actions_box = QVBoxLayout()
        sl.addLayout(self.actions_box)
        self.open_btn = QPushButton(icon("mdi6.target"), "Voir la brique")
        self.open_btn.setToolTip("Ferme le schéma et sélectionne la brique dans le pipeline")
        self.open_btn.clicked.connect(lambda: self._open_brick(self.view.selected))
        sl.addWidget(self.open_btn)
        split.addWidget(side)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([920, 440])
        lay.addWidget(split, 1)

        self.summary = muted("")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.view.zoom = float(self.size_combo.currentData())
        self.view.set_mode("3d" if saved == "3d" else "2d")
        self.refresh()

    # ------------------------------------------------------------------ état
    def _set_zoom(self, _index: int) -> None:
        zoom = float(self.size_combo.currentData())
        QSettings("DevOpsBuilder", "DevOpsBuilder").setValue("network/zoom", zoom)
        self.view.set_zoom(zoom)

    def _set_mode(self, mode: str) -> None:
        QSettings("DevOpsBuilder", "DevOpsBuilder").setValue("network/view", mode)
        self.view.set_mode(mode)

    def refresh(self) -> None:
        keep = self.view.selected
        self.graph = build_graph(self.project, self.catalog, self.engine, self.env.currentData())
        self.view.set_graph(self.graph, keep)
        self._fill_tree()
        counts = {s: sum(1 for f in self.graph.findings if f.severity is s) for s in Severity}
        parts = [count_text(counts[s], word) for s, word in ((Severity.BLOCKING, "erreur bloquante"),
                                                            (Severity.WARNING, "avertissement"),
                                                            (Severity.INFO, "information")) if counts[s]]
        text = (" · ".join(parts) if parts else "Aucun constat sur le schéma de cet environnement.")
        if self.graph.elsewhere:
            text += f" · {self.graph.elsewhere} autre(s) diagnostic(s) concernent la CI, la sécurité ou la plateforme : voir le panneau Diagnostics."
        self.summary.setText(text)
        self._show_detail(None)
        if self.view.selected:
            self._select_in_tree(self.view.selected)

    def _fill_tree(self) -> None:
        self.tree.clear()
        g = self.graph
        for layer in LAYERS:
            for node in g.layer(layer):
                found = g.findings_of(node.id)
                worst = g.worst(node.id)
                text = f"{node.label} ({LAYER_LABELS[layer].lower()})"
                if found:
                    text += " — " + ", ".join(f"{count_text(sum(1 for f in found if f.severity is s), SEVERITY_WORD[s])}"
                                              for s in Severity if any(f.severity is s for f in found))
                item = QTreeWidgetItem([plain(text)])
                item.setData(0, Qt.ItemDataRole.UserRole, ("node", node.id))
                if worst:
                    item.setIcon(0, icon(SEVERITY_ICONS[worst.value], theme.current().severity(worst.value)))
                item.setToolTip(0, self.view.describe(node.id))
                for f in found:
                    child = QTreeWidgetItem([plain(f"{SEVERITY_WORD[f.severity].capitalize()} : {f.message}")])
                    child.setData(0, Qt.ItemDataRole.UserRole, ("finding", g.findings.index(f)))
                    child.setIcon(0, icon(SEVERITY_ICONS[f.severity.value], theme.current().severity(f.severity.value)))
                    item.addChild(child)
                self.tree.addTopLevelItem(item)
                item.setExpanded(bool(found))

    def _select_in_tree(self, node_id: str) -> None:
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == ("node", node_id):
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(item)
                self.tree.blockSignals(False)
                return

    def _node_selected(self, node_id: str) -> None:
        self._select_in_tree(node_id)
        self._show_detail(("node", node_id))
        announce(self, self.view.describe(node_id))

    def _item_changed(self, item, _previous) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if data is None:
            return
        if data[0] == "node":
            self.view.select(data[1], emit=False)
        else:
            node_ids = self.graph.findings[data[1]].nodes
            if node_ids:
                self.view.select(node_ids[0], emit=False)
        self._show_detail(data)

    def _show_detail(self, data) -> None:
        clear_layout(self.actions_box)
        node_id, finding = None, None
        if data and data[0] == "node":
            node_id = data[1]
        elif data and data[0] == "finding":
            finding = self.graph.findings[data[1]]
            node_id = finding.nodes[0] if finding.nodes else None
        node = self.graph.node(node_id) if node_id else None
        self.open_btn.setEnabled(bool(node and node.bricks))
        if finding:
            self.detail.setText(f"{finding.message}\n(source : {finding.source})")
            for action in finding.actions:
                button = QPushButton(icon("mdi6.auto-fix"), plain(f"Corriger : {action.label}"))
                button.clicked.connect(lambda checked=False, a=action: self._fix(a))
                self.actions_box.addWidget(button)
        elif node:
            self.detail.setText(self.view.describe(node.id))
        else:
            self.detail.setText("Sélectionner un composant, dans le schéma ou dans la liste, pour voir ses constats.")

    def _fix(self, action: Action) -> None:
        if self.apply_fix is None:
            return
        self.project = self.apply_fix(action)
        self.refresh()

    def _open_brick(self, node_id: str | None) -> None:
        node = self.graph.node(node_id) if node_id and self.graph else None
        if node and node.bricks and self.focus_brick:
            self.accept()
            self.focus_brick(node.bricks[0])

    def save_image(self) -> None:
        name = f"reseau-{self.env.currentData()}-{self.view.mode}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le schéma", name, "Image PNG (*.png)")
        if path:
            self.view.grab().save(path if path.endswith(".png") else path + ".png")
