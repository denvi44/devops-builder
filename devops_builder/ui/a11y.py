# SPDX-License-Identifier: Apache-2.0
"""Accessibilité de l'interface : textes de Qt en français, annonces aux lecteurs d'écran, icônes décoratives.

Les lecteurs d'écran (NVDA, Orca, VoiceOver) lisent l'arbre d'accessibilité que Qt expose (UI Automation,
AT-SPI, NSAccessibility). Ce module couvre ce que Qt ne fait pas seul :
- les textes de Qt lui-même (boutons standard, menus contextuels, sélecteur de fichiers, docks) sont en
  anglais tant que sa traduction n'est pas chargée ;
- un message de la barre d'état n'est pas lu : il faut une annonce explicite ;
- une icône posée dans un QLabel est exposée comme une image sans nom, que le lecteur annonce.
"""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import QEvent, QLibraryInfo, QLocale, QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer, QTranslator
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent, QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

_translators: list[QTranslator] = []


def install_translations(app: QApplication) -> bool:
    """Charge la traduction française de Qt (qtbase) ; retourne False si elle est introuvable."""
    QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.France))
    if _translators:
        return True
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    ok = False
    for name in ("qtbase_fr", "qt_fr"):
        tr = QTranslator(app)
        if tr.load(name, path):
            app.installTranslator(tr)
            _translators.append(tr)
            ok = True
    return ok


def announce(source: QObject, text: str, assertive: bool = False) -> None:
    """Fait lire un message par le lecteur d'écran, sans déplacer le focus (WCAG 4.1.3, RGAA 7.5)."""
    if not text or not QAccessible.isActive():
        return
    event = QAccessibleAnnouncementEvent(source, text)
    event.setPoliteness(QAccessible.AnnouncementPoliteness.Assertive if assertive
                        else QAccessible.AnnouncementPoliteness.Polite)
    QAccessible.updateAccessibility(event)


class DecorativeIcon(QWidget):
    """Icône purement décorative : dessinée, sans être exposée comme une image aux technologies d'assistance.

    Un QLabel portant un pixmap devient une image sans nom, annoncée « image » ; un simple QWidget est un
    conteneur sans nom, que les lecteurs d'écran passent. L'icône est redessinée avec le thème courant.
    """

    def __init__(self, name: str, role: str = "primary", size: int = 20, parent: QWidget | None = None):
        super().__init__(parent)
        self.name, self.role, self.size_px = name, role, size
        self.setFixedSize(QSize(size, size))

    def paintEvent(self, event) -> None:  # noqa: N802
        from . import theme
        from .widgets import icon
        color = getattr(theme.current(), self.role, theme.current().primary)
        painter = QPainter(self)
        icon(self.name, color).paint(painter, QRect(0, 0, self.size_px, self.size_px))
        painter.end()


class FocusRing(QWidget):
    """Anneau de focus net (2 px, couleur principale, contraste d'au moins 3:1 sur le fond) autour du contrôle actif.

    Le thème Material ne marque le focus que par une légère teinte, invisible sur la plupart des contrôles
    (WCAG 2.4.7, RGAA 10.7). L'anneau est dessiné par-dessus la fenêtre, sans prendre la souris ni le focus,
    et suit le contrôle quand il bouge ou change de taille.
    """

    MARGIN = 3

    def __init__(self) -> None:
        super().__init__(None)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("focusRing")
        self.target: QWidget | None = None
        self.hide()

    def follow(self, old: QWidget | None, new: QWidget | None) -> None:
        if self.target is not None and shiboken6.isValid(self.target):
            self.target.removeEventFilter(self)
        self.target = new if isinstance(new, QWidget) and new is not self else None
        if self.target is None or self.target.window() is self.target:
            self.target = None
            self.hide()
            return
        self.target.installEventFilter(self)
        self.place()

    def place(self) -> None:
        t = self.target
        if t is None or not shiboken6.isValid(t) or not t.isVisible():
            self.target = None
            self.hide()
            return
        top = t.window()
        if self.parentWidget() is not top:
            self.setParent(top)
            # la fenêtre (un dialogue) sera détruite avant l'anneau : il la quitte à temps
            top.destroyed.connect(self._orphan)
        m = self.MARGIN
        rect = QRect(t.mapTo(top, QPoint(0, 0)), t.size()).adjusted(-m, -m, m, m)
        self.setGeometry(rect.intersected(top.rect()))
        self.raise_()
        self.show()
        self.update()

    def _orphan(self, *_) -> None:
        self.target = None
        self.hide()
        self.setParent(None)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.target and event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show,
                                                   QEvent.Type.Hide):
            QTimer.singleShot(0, self.place)
        return False

    def paintEvent(self, event) -> None:  # noqa: N802
        from . import theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(theme.current().primary), 2)
        painter.setPen(pen)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 4, 4)
        painter.end()


_ring: FocusRing | None = None


def install_focus_ring(app: QApplication) -> FocusRing:
    global _ring
    if _ring is None:
        _ring = FocusRing()
        app.focusChanged.connect(_ring.follow)
    return _ring
