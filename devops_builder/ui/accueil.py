# SPDX-License-Identifier: Apache-2.0
"""Écran d'accueil d'un projet vide (« Par où commencer ? ») et bandeau « Prochaine étape ».

Un projet vide affichait trois panneaux et un pipeline sans rien dedans : rien n'indiquait par où commencer.
L'accueil propose quatre départs, dont un seul est mis en avant ; il disparaît dès qu'une brique existe.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from . import theme


class StartCard(QPushButton):
    """Un départ possible : un titre, une phrase, et la touche d'action en entier."""

    def __init__(self, title: str, text: str, icon_name: str, primary: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("startCard")
        self.setProperty("recommended", primary)
        self.icon_name = icon_name
        self.setAccessibleName(title)
        self.setAccessibleDescription(text)
        self.setToolTip(text)
        self._base_height = theme.px(96)
        self.setMinimumHeight(self._base_height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.inner = lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 36, 12)
        lay.setSpacing(14)
        from .a11y import DecorativeIcon
        self.icon_widget = DecorativeIcon(icon_name, "primary", theme.px(32))
        lay.addWidget(self.icon_widget, 0, Qt.AlignmentFlag.AlignTop)
        box = QVBoxLayout()
        box.setSpacing(2)
        self.title_label = QLabel(title + ("  — conseillé" if primary else ""))
        self.title_label.setObjectName("startTitle")
        self.title_label.setWordWrap(True)
        self.text_label = QLabel(text)
        self.text_label.setObjectName("muted")
        self.text_label.setWordWrap(True)
        for label in (self.title_label, self.text_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            box.addWidget(label)
        lay.addLayout(box, 1)


    # Un bouton ne mesure pas la hauteur de ses textes repliés : on la lui donne (texte agrandi, fenêtre étroite).
    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return max(self._base_height, self.inner.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(theme.px(280), self._base_height)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(theme.px(600), self.heightForWidth(theme.px(600)))

    def event(self, event) -> bool:  # noqa: N802
        # Les mises en page imbriquées ne transmettent pas la hauteur d'un texte replié : la carte la réclame
        # elle-même à chaque changement de largeur, de police ou de contenu.
        done = super().event(event)
        if event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest, QEvent.Type.FontChange,
                            QEvent.Type.StyleChange, QEvent.Type.Show):
            wanted = self.heightForWidth(self.width())
            if wanted != self.minimumHeight():
                self.setMinimumHeight(wanted)
        return done


class WelcomePanel(QFrame):
    """« Par où commencer ? » : assistant, modèle de fournisseur, exemple, ou pipeline à la main."""

    wizardRequested = Signal()
    templateRequested = Signal(str)
    exampleRequested = Signal(object)
    openRequested = Signal()
    manualRequested = Signal()

    def __init__(self, templates: list[tuple[str, str, str]], examples: list[tuple[str, object]],
                 parent: QWidget | None = None):
        """templates : (slug, titre, description) ; examples : (nom, chemin)."""
        super().__init__(parent)
        self.setObjectName("welcome")
        self.setAccessibleName("Par où commencer ?")
        # défilement vertical : texte agrandi ou petit écran, les cinq départs restent atteignables
        frame = QVBoxLayout(self)
        frame.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("welcomeScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAccessibleName("Points de départ")
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # le focus va aux cartes, pas à la zone de défilement
        scroll.viewport().setAutoFillBackground(False)
        frame.addWidget(scroll)
        content = QWidget()
        content.setObjectName("welcomeContent")
        scroll.setWidget(content)
        page = QHBoxLayout(content)   # colonne centrée, d'une largeur lisible sur un grand écran
        page.setContentsMargins(24, 16, 24, 16)
        page.addStretch(1)
        column = QWidget()
        column.setObjectName("welcomeContent")
        column.setMaximumWidth(theme.px(860))
        column.setMinimumWidth(theme.px(300))
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        page.addWidget(column, 100)
        page.addStretch(1)
        outer = QVBoxLayout(column)
        outer.setContentsMargins(0, 28, 0, 28)
        outer.setSpacing(10)
        outer.addStretch(1)
        title = QLabel("Par où commencer ?")
        title.setObjectName("heroTitle")
        title.setAccessibleName("Par où commencer ?")
        outer.addWidget(title)
        lead = QLabel("Un pipeline DevOps se compose en quelques minutes : choisissez un point de départ, "
                      "tout reste modifiable ensuite.")
        lead.setObjectName("muted")
        lead.setWordWrap(True)
        outer.addWidget(lead)
        outer.addSpacing(8)

        self.wizard = StartCard("Me laisser guider par l'assistant",
                                "Cinq questions (application, forge, hébergement, environnements, options) et le pipeline "
                                "est construit. Le plus simple si vous débutez.",
                                "mdi6.wizard-hat", primary=True)
        self.wizard.clicked.connect(self.wizardRequested)
        self.template = StartCard("Partir d'un modèle de fournisseur cloud",
                                  "AWS, Google Cloud, Azure, OVHcloud, Scaleway ou Outscale : Kubernetes, serverless "
                                  "ou machines, avec les services du fournisseur.",
                                  "mdi6.cloud-outline")
        menu = QMenu(self.template)
        menu.setToolTipsVisible(True)
        for slug, label, tip in templates:
            action = menu.addAction(label, lambda checked=False, s=slug: self.templateRequested.emit(s))
            action.setToolTip(tip)
        self.template.setMenu(menu)
        self.example = StartCard("Ouvrir un exemple",
                                 "Un pipeline déjà composé, à parcourir ou à adapter.", "mdi6.lightbulb-outline")
        menu = QMenu(self.example)
        for name, path in examples:
            menu.addAction(name, lambda checked=False, p=path: self.exampleRequested.emit(p))
        self.example.setMenu(menu)
        self.existing = StartCard("Ouvrir un projet enregistré",
                                  "Un fichier .devops.yaml créé plus tôt.", "mdi6.folder-open-outline")
        self.existing.clicked.connect(self.openRequested)
        self.manual = StartCard("Construire à la main",
                                "Ouvre le catalogue : glisser les outils dans les étapes du pipeline, ou double-clic "
                                "pour les ajouter.", "mdi6.puzzle-outline")
        self.manual.clicked.connect(self.manualRequested)
        self.cards = [self.wizard, self.template, self.example, self.existing, self.manual]
        for card in self.cards:
            outer.addWidget(card)
        outer.addStretch(2)
        for first, second in zip(self.cards, self.cards[1:], strict=False):
            self.setTabOrder(first, second)

    def update_icons(self) -> None:
        for card in self.cards:
            card.icon_widget.update()


class NextStep(QFrame):
    """Un seul conseil à la fois : le prochain geste utile, avec son bouton."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("nextStep")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(10)
        self.label = QLabel()
        self.label.setObjectName("nextStepText")
        self.label.setWordWrap(True)
        self.button = QPushButton()
        self.button.setProperty("class", "success")
        lay.addWidget(self.label, 1)
        lay.addWidget(self.button)
        self._slot = None
        self.button.clicked.connect(lambda: self._slot and self._slot())

    def set_step(self, text: str, button: str, slot, tone: str = "info") -> None:
        self.label.setText("Prochaine étape : " + text)
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)
        self.button.setText(button)
        self.button.setAccessibleName(f"{button} — {text}")
        self._slot = slot


def next_step(project, diags, severity_blocking) -> tuple[str, str, str, str]:
    """(texte, bouton, action, ton) du prochain geste, d'après le projet et ses diagnostics.

    action : « diagnostics », « application » ou « generer ».
    """
    blocking = sum(1 for d in diags if d.severity is severity_blocking)
    if blocking:
        return (f"corriger {blocking} erreur{'s' if blocking > 1 else ''} bloquante{'s' if blocking > 1 else ''}, "
                "sans quoi les fichiers ne se génèrent pas.", "Voir les erreurs", "diagnostics", "blocking")
    values = sum(1 for d in diags if d.rule_id == "R34")
    if values:
        return ("renseigner les valeurs d'exemple (nom du cluster, adresse publique…) : sélectionner la brique "
                "signalée, puis le panneau Propriétés.", "Voir lesquelles", "diagnostics", "warning")
    if not project.app.source:
        return ("désigner le dossier de votre application, pour y lire le langage, le port et la base.",
                "Choisir le dossier", "application", "info")
    return ("le pipeline est prêt : générer les fichiers.", "Générer", "generer", "ok")
