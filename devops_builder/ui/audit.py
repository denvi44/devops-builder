# SPDX-License-Identifier: Apache-2.0
"""Audit d'accessibilité automatisé de l'interface, sur l'arbre que Qt expose aux technologies d'assistance.

Chaque contrôle renvoie des constats (critère, fenêtre, élément, problème). Les critères suivent l'EN 301 549
(chapitre 11, logiciels), qui reprend les critères WCAG 2.1 ; le RGAA, écrit pour le web, est cité quand un
critère correspond. Ce qui ne se mesure pas automatiquement (pertinence des noms, restitution réelle par
NVDA, Orca ou VoiceOver, agrandissement à 200 % sur chaque dialogue) reste à vérifier à la main : voir
docs/accessibilite.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QEventLoop, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QAccessible, QAction, QColor, QImage, QKeySequence
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QRadioButton,
    QScrollArea,
    QScrollBar,
    QSlider,
    QTabBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QToolButton,
    QWidget,
)

# critère → (EN 301 549, WCAG, RGAA)
CRITERIA = {
    "nom": ("11.4.1.2", "4.1.2 Nom, rôle et valeur", "RGAA 11.1, 7.1"),
    "clavier": ("11.2.1.1", "2.1.1 Clavier", "RGAA 7.3"),
    "focus": ("11.2.4.7", "2.4.7 Visibilité du focus", "RGAA 10.7"),
    "contraste": ("11.1.4.3", "1.4.3 Contraste (minimum)", "RGAA 3.2"),
    "titre": ("11.2.4.2", "2.4.2 Titre de page (fenêtre)", "RGAA 8.5"),
    "langue": ("11.3.1.2", "3.1.2 Langue d'un passage", "RGAA 8.7"),
    "raccourcis": ("11.2.1.4", "2.1.4 Raccourcis clavier", "RGAA 12.10"),
    "agrandissement": ("11.1.4.4", "1.4.4 Redimensionnement du texte", "RGAA 10.4"),
}

INTERACTIVE = (QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox, QAbstractItemView, QTextEdit,
               QPlainTextEdit, QSlider, QTabBar, QTabWidget, QAbstractScrollArea)
# mots de l'interface de Qt laissés en anglais quand sa traduction n'est pas chargée
ENGLISH = re.compile(r"^(OK|Cancel|Close|Float|Open|Save|Discard|Apply|Reset|Yes|No|Help|Next|Back|Finish|"
                     r"Commit|Done|Restore Defaults|Closes the dock widget|Undocks and re-attaches the dock widget|"
                     r"&?Undo|&?Redo|Cu&t|&Copy|&Paste|Delete|Select All)$")


@dataclass
class Finding:
    criterion: str
    window: str
    element: str
    problem: str

    def __str__(self) -> str:
        return f"[{self.criterion}] {self.window} › {self.element} : {self.problem}"


def name_of(w: QWidget) -> str:
    iface = QAccessible.queryAccessibleInterface(w)
    return iface.text(QAccessible.Text.Name).strip() if iface else ""


def _label(w: QWidget) -> str:
    return f"{type(w).__name__}" + (f" « {name_of(w)} »" if name_of(w) else "") + \
        (f" #{w.objectName()}" if w.objectName() and not w.objectName().startswith("qt_") else "")


def _window_name(root: QWidget) -> str:
    return root.windowTitle() or type(root).__name__


def _internal(w: QWidget) -> bool:
    """Pièce interne d'un contrôle composé, exposée par son parent (zone de saisie d'un champ numérique…)."""
    if w.objectName().startswith("qt_"):
        return True
    if isinstance(w, (QHeaderView, QScrollBar)):
        return True
    parent = w.parentWidget()
    return isinstance(w, QLineEdit) and isinstance(parent, (QComboBox, QAbstractSpinBox))


def interactive(root: QWidget) -> list[QWidget]:
    out = []
    for w in [root, *root.findChildren(QWidget)]:
        if w.isVisible() and isinstance(w, INTERACTIVE) and not _internal(w):
            if isinstance(w, (QAbstractScrollArea, QTabWidget)) \
                    and not isinstance(w, (QAbstractItemView, QTextEdit, QPlainTextEdit)) \
                    and not (w.focusPolicy() & Qt.FocusPolicy.TabFocus):
                continue  # conteneur hors de la tabulation (défilement, onglets) : rien à nommer
            out.append(w)
    return out


def check_names(root: QWidget) -> list[Finding]:
    return [Finding("nom", _window_name(root), _label(w), "pas de nom accessible")
            for w in interactive(root) if not name_of(w)]


def _in_menus(action: QAction, window: QWidget) -> bool:
    menus = window.findChildren(QMenu)
    return any(action in m.actions() for m in menus) or not action.shortcut().isEmpty()


def check_keyboard(root: QWidget) -> list[Finding]:
    found = []
    for w in interactive(root):
        if not w.isEnabled() or w.focusPolicy() & Qt.FocusPolicy.TabFocus:
            continue
        group = w.group() if isinstance(w, QRadioButton) else None
        if group is not None and group.exclusive() and any(
                b.isVisible() and b.focusPolicy() & Qt.FocusPolicy.TabFocus for b in group.buttons()):
            continue  # bouton radio : Tab atteint le groupe, les flèches parcourent les choix (comportement standard)
        if isinstance(w, QToolButton) and isinstance(w.parentWidget(), QToolBar):
            action = w.defaultAction()
            if action is not None and _in_menus(action, root.window()):
                continue  # bouton de barre d'outils : la même action est au menu ou a un raccourci
        found.append(Finding("clavier", _window_name(root), _label(w), "inaccessible par la touche Tab"))
    return found


def check_title(root: QWidget) -> list[Finding]:
    if isinstance(root, (QDialog, QMainWindow)) and not root.windowTitle().strip():
        return [Finding("titre", type(root).__name__, "fenêtre", "pas de titre")]
    return []


def check_language(root: QWidget) -> list[Finding]:
    found = []
    widgets = [w for w in [root, *root.findChildren(QWidget)] if w.isVisible()]
    for w in widgets:
        iface = QAccessible.queryAccessibleInterface(w)
        if iface is None:
            continue
        for text in (iface.text(QAccessible.Text.Name), iface.text(QAccessible.Text.Description)):
            if text and ENGLISH.match(text.strip()):
                found.append(Finding("langue", _window_name(root), _label(w), f"texte de Qt en anglais : « {text} »"))
    return found


def check_shortcuts(window: QWidget) -> list[Finding]:
    found, seen = [], {}
    for a in window.findChildren(QAction):
        for seq in a.shortcuts():
            key = seq.toString(QKeySequence.SequenceFormat.PortableText)
            if not key:
                continue
            label = a.text().replace("&", "") or a.toolTip()
            if key in seen and seen[key] != label:
                found.append(Finding("raccourcis", _window_name(window), key, f"partagé par « {seen[key]} » et « {label} »"))
            seen.setdefault(key, label)
            mods = seq[0].keyboardModifiers()
            k = seq[0].key()
            if mods == Qt.KeyboardModifier.NoModifier and Qt.Key.Key_Space <= k <= Qt.Key.Key_AsciiTilde:
                found.append(Finding("raccourcis", _window_name(window), key,
                                     f"raccourci d'une seule touche caractère (« {label} »)"))
    return found


def check_clipped(root: QWidget) -> list[Finding]:
    """Texte coupé : libellé ou bouton plus petit que ce que demande son texte (à 200 %, WCAG 1.4.4)."""
    found = []
    for w in [root, *root.findChildren(QWidget)]:
        if not w.isVisible() or not isinstance(w, (QLabel, QAbstractButton)):
            continue
        text = w.text()
        if not text or not text.strip() or (isinstance(w, QLabel) and w.pixmap() and not w.pixmap().isNull()):
            continue
        hint = w.sizeHint()
        if isinstance(w, QLabel) and w.wordWrap():
            short = w.heightForWidth(w.width()) > w.height() + 2
        else:
            short = hint.width() > w.width() + 2 or hint.height() > w.height() + 4
        if short:
            found.append(Finding("agrandissement", _window_name(root), _label(w) + f" « {text[:40]} »",
                                 f"texte coupé ({w.width()}×{w.height()} pour {hint.width()}×{hint.height()})"))
    return found


# ------------------------------------------------------------------ couleurs
def luminance(c: QColor) -> float:
    def channel(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(c.red()) + 0.7152 * channel(c.green()) + 0.0722 * channel(c.blue())


def ratio(a: QColor | str, b: QColor | str) -> float:
    la, lb = luminance(QColor(a)), luminance(QColor(b))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def blend(fg: str, bg: str, alpha: int) -> QColor:
    f, b = QColor(fg), QColor(bg)
    t = alpha / 255
    return QColor(round(f.red() * t + b.red() * (1 - t)), round(f.green() * t + b.green() * (1 - t)),
                  round(f.blue() * t + b.blue() * (1 - t)))


def snapshot(w: QWidget, margin: int = 0) -> QImage:
    """Rendu du contrôle tel qu'il apparaît, fond de ses parents compris (un grab seul serait transparent) ;
    avec une marge, ce qui l'entoure aussi (anneau de focus)."""
    top = w.window()
    rect = QRect(w.mapTo(top, QPoint(0, 0)), w.size()).adjusted(-margin, -margin, margin, margin)
    return top.grab(rect.intersected(top.rect())).toImage()


def _dominant_and_extreme(img: QImage) -> tuple[QColor, QColor] | None:
    counts: dict[int, int] = {}
    for y in range(img.height()):
        for x in range(img.width()):
            rgb = img.pixel(x, y) & 0xFFFFFF
            counts[rgb] = counts.get(rgb, 0) + 1
    if len(counts) < 2:
        return None
    bg = QColor(max(counts, key=counts.get))
    # couleur du texte : la plus éloignée du fond parmi celles qui couvrent au moins quelques pixels
    present = [QColor(c) for c, n in counts.items() if n >= 3]
    text = max(present, key=lambda c: ratio(c, bg))
    return bg, text


def check_rendered_text(root: QWidget) -> list[Finding]:
    """Contraste du texte tel qu'il est dessiné : fond dominant contre pixel du texte le plus contrasté."""
    found = []
    for w in [root, *root.findChildren(QWidget)]:
        if not w.isVisible() or not w.isEnabled() or w.width() < 4 or w.height() < 4:
            continue
        text = w.text() if isinstance(w, (QLabel, QAbstractButton)) else ""
        if not isinstance(text, str) or not text.strip() or (isinstance(w, QLabel) and w.pixmap() and not w.pixmap().isNull()):
            continue
        if w.visibleRegion().boundingRect().size() != w.size():
            continue  # en partie masqué (défilement) : la capture ne montrerait pas le contrôle
        res = _dominant_and_extreme(snapshot(w))
        if res is None:
            continue
        bg, fg = res
        # Couleur du texte : celle que déclare la feuille de style (le lissage éclaircit les pixels des glyphes fins,
        # et une icône plus sombre tromperait la mesure) ; mesurée seulement pour un texte riche à plusieurs couleurs
        rich = isinstance(w, QLabel) and (w.textFormat() == Qt.TextFormat.RichText or Qt.mightBeRichText(text))
        if not rich:
            fg = w.palette().color(w.foregroundRole())
        font = w.font()
        large = font.pointSizeF() >= 18 or (font.bold() and font.pointSizeF() >= 14)
        need = 3.0 if large else 4.5
        r = ratio(fg, bg)
        if r < need:
            found.append(Finding("contraste", _window_name(root), _label(w) + f" « {text[:40]} »",
                                 f"{r:.2f}:1 ({fg.name()} sur {bg.name()}), {need}:1 attendu"))
    return found


def palette_pairs(p) -> list[tuple[str, str, str, float]]:
    """Couples dessinés à la main (cartes du canevas, puces, diagnostics) : (nom, texte, fond, seuil)."""
    sel = blend(p.primary, p.background, 34).name()
    hover = blend(p.primary, p.background, 22).name()
    pairs = [("texte", p.text, p.background, 4.5), ("texte sur carte", p.text, p.surface, 4.5),
             ("texte secondaire", p.text_muted, p.background, 4.5),
             ("texte secondaire sur carte", p.text_muted, p.surface, 4.5),
             ("brique sélectionnée", p.text, sel, 4.5), ("sous-titre de brique sélectionnée", p.text_muted, sel, 4.5),
             ("brique survolée", p.text_muted, hover, 4.5),
             ("puce principale", p.primary, p.background, 4.5), ("lien", p.primary, p.surface, 4.5)]
    for sev in ("blocking", "warning", "info", "ok"):
        pairs.append((f"texte {sev} (résumé des diagnostics)", getattr(p, sev), p.background, 4.5))
        pairs.append((f"texte {sev} sur carte", getattr(p, sev), p.surface, 4.5))
        pairs.append((f"icône {sev}", getattr(p, sev), p.surface, 3.0))      # composant graphique : 3:1
        pairs.append((f"icône {sev} sur brique", getattr(p, sev), p.background, 3.0))
    pairs.append(("bord de brique au focus", p.primary, p.border, 3.0))
    return pairs


def check_palettes() -> list[Finding]:
    from . import theme
    found = []
    for pal in (theme.LIGHT, theme.DARK):
        label = "thème sombre" if pal.dark else "thème clair"
        for name, fg, bg, need in palette_pairs(pal):
            r = ratio(fg, bg)
            if r < need:
                found.append(Finding("contraste", label, name, f"{r:.2f}:1 ({fg} sur {bg}), {need}:1 attendu"))
    return found


# ------------------------------------------------------------------ focus visible
def _wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def focus_change(w: QWidget, sink: QWidget) -> int:
    """Pixels qui changent avec un contraste d'au moins 3:1 quand le contrôle prend le focus."""
    sink.setFocus()
    QApplication.processEvents()
    # Tab amène le contrôle dans la zone visible d'un défilement ; setFocus ne le fait pas
    ancestor = w.parentWidget()
    while ancestor is not None:
        if isinstance(ancestor, QScrollArea):
            ancestor.ensureWidgetVisible(w)
        ancestor = ancestor.parentWidget()
    QApplication.processEvents()
    before = snapshot(w, 4)
    w.setFocus()
    QApplication.processEvents()
    _wait(80)  # l'anneau revérifie sa place toutes les 60 ms
    after = snapshot(w, 4)
    if not w.hasFocus():
        return -1
    n = 0
    for y in range(min(before.height(), after.height())):
        for x in range(min(before.width(), after.width())):
            a, b = before.pixel(x, y), after.pixel(x, y)
            if a != b and ratio(QColor(a), QColor(b)) >= 3:
                n += 1
    return n


def check_focus_visible(root: QWidget, sink: QWidget, sample: int = 3) -> list[Finding]:
    """Un échantillon de chaque type de contrôle : l'indicateur de focus doit tracer au moins une ligne."""
    found, seen = [], {}
    for w in interactive(root):
        if not w.isEnabled() or not (w.focusPolicy() & Qt.FocusPolicy.TabFocus) or w is sink:
            continue
        kind = type(w).__name__
        if seen.get(kind, 0) >= sample:
            continue
        seen[kind] = seen.get(kind, 0) + 1
        n = focus_change(w, sink)
        if 0 <= n < min(w.width(), w.height()):
            found.append(Finding("focus", _window_name(root), _label(w), f"focus peu visible ({n} pixels changent à 3:1)"))
    return found


def audit_window(root: QWidget, sink: QWidget | None = None, focus: bool = True) -> list[Finding]:
    found = [*check_title(root), *check_names(root), *check_keyboard(root), *check_language(root),
             *check_rendered_text(root)]
    if focus and sink is not None:
        found += check_focus_visible(root, sink)
    return found


# ------------------------------------------------------------------ parcours de toute l'interface
def dialogs_of(win) -> list[tuple[str, object]]:
    """Fabriques des dialogues de l'application, pour le projet ouvert dans la fenêtre."""
    from . import application, data, dialogs, export, fiche, maintenance, ports, validation, wizard
    result = win._generation()
    out = [
        ("Paramètres du projet", lambda: dialogs.ProjectSettingsDialog(win.project, win, win.catalog)),
        ("Application", lambda: application.ApplicationDialog(win.project, win.catalog, win)),
        ("Ports", lambda: ports.PortsDialog(win.project, win.catalog, win)),
        ("Données", lambda: data.DataDialog(win.project, win.catalog, win.engine, win)),
        ("Entretien du catalogue", lambda: maintenance.MaintenanceDialog(win.catalog, win.project, win)),
        ("Assistant", lambda: wizard.StarterWizard(win.catalog, win.engine, win)),
        ("Fiche", lambda: fiche.FicheDialog(win.catalog, {"id": "", "name": "", "stage": "build", "license": "unknown"},
                                            parent=win)),
    ]
    if result is not None:
        out += [("Génération", lambda: dialogs.GenerateDialog(result, win)),
                ("Validation", lambda: validation.ValidationDialog(result, win)),
                ("Export Git", lambda: export.GitExportDialog(result, win)),
                ("Test dans kind", lambda: validation.KindTestDialog(result, win))]
    return out


def clipped_at(win, factor: float, screen=(1920, 1080)) -> list[Finding]:
    """Texte coupé à une taille de texte donnée, fenêtre et dialogues à la taille d'un écran de 1920×1080."""
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QWizard
    limit = QSize(*screen)
    before = win.size()
    win.set_text_scale(factor)
    win.resize(limit)
    QApplication.processEvents()
    found = check_clipped(win)
    for _label, make in dialogs_of(win):
        dlg = make()
        dlg.show()
        dlg.resize(dlg.sizeHint().expandedTo(dlg.size()).boundedTo(limit))
        QApplication.processEvents()
        for page in (dlg.pageIds() if isinstance(dlg, QWizard) else [None]):
            if page is not None and page != dlg.currentId():
                dlg.next()
                QApplication.processEvents()
            found += check_clipped(dlg)
        dlg.close()
        dlg.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    win.set_text_scale(1.0)
    win.resize(before)
    QApplication.processEvents()
    return found


def full_audit(win, focus: bool = True) -> list[Finding]:
    """Fenêtre principale et chaque dialogue, dans le thème courant ; plus les palettes des deux thèmes."""
    from PySide6.QtWidgets import QMessageBox, QWizard
    found = [*audit_window(win, win.palette.search, focus), *check_shortcuts(win)]
    for _label, make in dialogs_of(win):
        dlg = make()
        dlg.show()
        QApplication.processEvents()
        pages = [None]
        if isinstance(dlg, QWizard):
            pages = dlg.pageIds()
        for page in pages:
            if page is not None and page != dlg.currentId():
                dlg.next()
                QApplication.processEvents()
            sink = next((w for w in interactive(dlg) if isinstance(w, QAbstractButton) and w.isEnabled()), None)
            found += [f for f in audit_window(dlg, sink, focus) if f not in found]
        dlg.close()
        dlg.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    # boutons standard d'une boîte de message : traduits par Qt
    box = QMessageBox(QMessageBox.Icon.Question, "Enregistrer ?", "Le projet a changé.",
                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                      | QMessageBox.StandardButton.Cancel, win)
    box.show()
    QApplication.processEvents()
    found += check_language(box)
    box.close()
    return found + check_palettes()
