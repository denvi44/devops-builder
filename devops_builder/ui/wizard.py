"""Assistant de démarrage : quelques questions, un pipeline complet et cohérent."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ..catalog import Catalog
from ..model import ENV_PRESETS, LANGUAGES, STAGE_LABELS, Project
from ..rules import RuleEngine
from ..starter import (
    CLOUDS,
    FORGES,
    HOSTINGS,
    IAC,
    NATIVE_CI,
    OBSERVABILITY,
    StarterAnswers,
    build_starter,
    clouds_for,
    validate,
)
from .widgets import muted, plain


def _radios(options: dict[str, str], layout: QVBoxLayout, default: str) -> QButtonGroup:
    group = QButtonGroup(layout.parentWidget())
    for i, (key, label) in enumerate(options.items()):
        rb = QRadioButton(plain(label))
        rb.setProperty("key", key)
        rb.setChecked(key == default)
        group.addButton(rb, i)
        layout.addWidget(rb)
    return group


def _checked(group: QButtonGroup) -> str:
    b = group.checkedButton()
    return b.property("key") if b else ""


class StarterWizard(QWizard):
    def __init__(self, catalog: Catalog, engine: RuleEngine, parent: QWidget | None = None):
        super().__init__(parent)
        self.catalog, self.engine = catalog, engine
        self.setWindowTitle("Nouveau projet")
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage)
        for btn, text in ((QWizard.WizardButton.NextButton, "Suivant"), (QWizard.WizardButton.BackButton, "Précédent"),
                          (QWizard.WizardButton.FinishButton, "Créer le projet"),
                          (QWizard.WizardButton.CancelButton, "Annuler")):
            self.setButtonText(btn, text)
        self.resize(720, 560)
        self.addPage(self._page_project())
        self.addPage(self._page_code())
        self.addPage(self._page_hosting())
        self.addPage(self._page_options())
        self.summary_page = self._page_summary()
        self.addPage(self.summary_page)

    # ------------------------------------------------------------------ pages
    def _page(self, title: str, subtitle: str) -> tuple[QWizardPage, QVBoxLayout]:
        page = QWizardPage()
        page.setTitle(title)
        page.setSubTitle(subtitle)
        return page, QVBoxLayout(page)

    def _page_project(self) -> QWizardPage:
        page, lay = self._page("Application", "Le dossier de l'application à mettre en pipeline : son analyse "
                                              "pré-remplit les réponses suivantes.")
        from .application import FolderPicker
        self.w_folder = FolderPicker()
        self.w_folder.scan.clicked.connect(self.analyse)
        lay.addWidget(self.w_folder)
        self.w_found = muted("Facultatif : sans dossier, les réponses partent des valeurs par défaut.")
        self.w_found.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.w_found)
        self.profile = None
        form = QFormLayout()
        self.w_name = QLineEdit("Mon projet")
        self.w_language = QComboBox()
        for k, v in LANGUAGES.items():
            self.w_language.addItem(v, k)
        self.w_image = QLineEdit("mon-app")
        self.w_port = QSpinBox()
        self.w_port.setRange(1, 65535)
        self.w_port.setValue(8000)
        for label, w in (("Nom", self.w_name), ("Langage", self.w_language),
                         ("Nom de l'image", self.w_image), ("Port de l'application", self.w_port)):
            w.setAccessibleName(label)
            form.addRow(label, w)
        lay.addLayout(form)
        return page

    def _page_code(self) -> QWizardPage:
        page, lay = self._page("Code et intégration continue", "Où vit le code ; la CI native de la forge est choisie.")
        self.g_forge = _radios(FORGES, lay, "gitlab")
        self.ci_label = muted("")
        lay.addWidget(self.ci_label)
        lay.addStretch(1)
        self.g_forge.buttonToggled.connect(lambda *_: self._update_ci_label())
        self._update_ci_label()
        return page

    def analyse(self) -> None:
        from .. import appscan
        from ..starter import answers_from_profile
        path = self.w_folder.path()
        if not path:
            self.w_found.setText("Choisir d'abord le dossier de l'application.")
            return
        try:
            self.profile = appscan.scan(path)
        except ValueError as exc:
            self.w_found.setText(str(exc))
            return
        a, taken = answers_from_profile(self.profile, self.catalog, self.collect())
        self.w_name.setText(a.name)
        self.w_language.setCurrentIndex(max(0, self.w_language.findData(a.language)))
        self.w_image.setText(a.image_name)
        self.w_port.setValue(a.port)
        for group, key in ((self.g_forge, a.forge), (self.g_hosting, a.hosting)):
            for b in group.buttons():
                b.setChecked(b.property("key") == key)
        if hasattr(self, "w_iac") and a.iac:
            self.w_iac.setCurrentIndex(max(0, self.w_iac.findData(a.iac)))
        if hasattr(self, "w_deps"):
            self.w_deps.setChecked(a.dependencies)
        self._answers = a
        lines = "".join(f"<li>{line}</li>" for line in self.profile.summary())
        self.w_found.setText(f"<b>Repris :</b> {', '.join(taken)}.<ul style='margin:4px 0'>{lines}</ul>")

    def _update_ci_label(self) -> None:
        ci = self.catalog.get(NATIVE_CI.get(_checked(self.g_forge), ""))
        self.ci_label.setText(f"CI : {ci.name}" if ci else "")

    def _page_hosting(self) -> QWizardPage:
        page, lay = self._page("Hébergement", "Où tourne l'application en production.")
        self.g_hosting = _radios(HOSTINGS, lay, "docker-host")
        self.w_secnum = QCheckBox("Exiger un hébergement qualifié SecNumCloud")
        lay.addWidget(self.w_secnum)
        form = QFormLayout()
        self.w_cloud = QComboBox()
        self.w_cloud.setAccessibleName("Cloud")
        form.addRow("Cloud", self.w_cloud)
        lay.addLayout(form)
        self.hosting_error = QLabel()
        self.hosting_error.setWordWrap(True)
        self.hosting_error.setStyleSheet("color: #d32f2f;")
        lay.addWidget(self.hosting_error)
        lay.addStretch(1)
        self.g_hosting.buttonToggled.connect(lambda *_: self._update_clouds())
        self.w_secnum.toggled.connect(lambda *_: self._update_clouds())
        self._update_clouds()
        page.validatePage = self._validate_hosting  # type: ignore[method-assign]
        return page

    def _update_clouds(self) -> None:
        current = self.w_cloud.currentData()
        self.w_cloud.clear()
        options = clouds_for(_checked(self.g_hosting), self.w_secnum.isChecked())
        for c in options:
            self.w_cloud.addItem(CLOUDS[c], c)
        if current in options:
            self.w_cloud.setCurrentIndex(options.index(current))
        self.w_cloud.setEnabled(bool(options))
        problems = validate(self.collect())
        self.hosting_error.setText(" ".join(problems))

    def _validate_hosting(self) -> bool:
        problems = validate(self.collect())
        self.hosting_error.setText(" ".join(problems))
        return not problems

    def _page_options(self) -> QWizardPage:
        page, lay = self._page("Environnements et options", "Promotion entre environnements et contrôles à inclure.")
        lay.addWidget(muted("Environnements"))
        self.g_envs = _radios(ENV_PRESETS, lay, "staging-prod")
        self.w_shared = QCheckBox("Environnements hors production sur un même hôte Docker (ports décalés)")
        self.w_shared.setToolTip("Les ports publiés de chaque environnement hors production sont décalés de 10 000 "
                                 "pour qu'ils cohabitent sur la même machine.")
        lay.addWidget(self.w_shared)
        self.w_gitops = QCheckBox("Déploiement GitOps avec Argo CD (Kubernetes)")
        self.w_security = QCheckBox("Sécurité : secrets (Gitleaks), vulnérabilités (Trivy), signature (Cosign)")
        self.w_security.setChecked(True)
        self.w_quality = QCheckBox("Qualité du code (SonarQube)")
        self.w_deps = QCheckBox("Mises à jour des dépendances (Renovate ou Dependabot)")
        self.w_deps.setChecked(True)
        for w in (self.w_gitops, self.w_security, self.w_quality, self.w_deps):
            lay.addWidget(w)
        form = QFormLayout()
        self.w_obs = QComboBox()
        for k, v in OBSERVABILITY.items():
            self.w_obs.addItem(v, k)
        self.w_iac = QComboBox()
        for k, v in IAC.items():
            self.w_iac.addItem(v, k)
        form.addRow("Observabilité", self.w_obs)
        form.addRow("Infrastructure as code (cloud)", self.w_iac)
        lay.addLayout(form)
        lay.addStretch(1)
        page.initializePage = self._init_options  # type: ignore[method-assign]
        return page

    def _init_options(self) -> None:
        a = self.collect()
        k8s = a.hosting in ("kubernetes", "kubernetes-managed")
        self.w_gitops.setEnabled(k8s)
        if not k8s:
            self.w_gitops.setChecked(False)
        self.w_iac.setEnabled(a.cloud is not None)
        docker = a.hosting in ("docker-host", "vm")
        self.w_shared.setEnabled(docker)
        if not docker:
            self.w_shared.setChecked(False)

    def _page_summary(self) -> QWizardPage:
        page, lay = self._page("Récapitulatif", "Le pipeline qui sera créé ; tout reste modifiable ensuite.")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        lay.addStretch(1)
        page.initializePage = self._init_summary  # type: ignore[method-assign]
        return page

    def _init_summary(self) -> None:
        project = self.project()
        rows = []
        for stage, label in STAGE_LABELS.items():
            names = [self.catalog[b.tool].name for b in project.stages.get(stage, [])]
            if names:
                rows.append(f"<tr><td><b>{label}</b>&nbsp;&nbsp;</td><td>{', '.join(names)}</td></tr>")
        envs = " → ".join(e.display + (" (approbation)" if e.approval else "") for e in project.environments)
        hosts = {e.host for e in project.environments if e.host}
        if hosts:
            envs += " ; hors production sur un même hôte, ports décalés"
        diags = self.engine.evaluate(project)
        warn = sum(1 for d in diags if d.severity.value == "avertissement")
        tail = f"<p>{warn} avertissement(s) à examiner, aucun blocage.</p>" if warn else "<p>Aucun blocage.</p>"
        self.summary.setText(f"<p>Environnements : {envs}</p><table>{''.join(rows)}</table>{tail}")

    # ---------------------------------------------------------------- résultat
    def collect(self) -> StarterAnswers:
        a = self._collect()
        detected = getattr(self, "_answers", None)
        if detected is not None:  # ce que l'analyse a vu et que l'assistant ne demande pas
            a.ci = detected.ci if detected.forge == a.forge else None
            a.dockerfile, a.k8s_deploy = detected.dockerfile, detected.k8s_deploy
            a.dependency_tool, a.source = detected.dependency_tool, detected.source
        return a

    def _collect(self) -> StarterAnswers:
        return StarterAnswers(
            name=self.w_name.text(), language=self.w_language.currentData(), image_name=self.w_image.text(),
            port=self.w_port.value(), forge=_checked(self.g_forge), hosting=_checked(self.g_hosting),
            cloud=self.w_cloud.currentData() if self.w_cloud.isEnabled() else None,
            secnumcloud=self.w_secnum.isChecked(),
            envs=_checked(self.g_envs) if hasattr(self, "g_envs") else "staging-prod",
            gitops=self.w_gitops.isChecked() if hasattr(self, "w_gitops") else False,
            security=self.w_security.isChecked() if hasattr(self, "w_security") else True,
            quality=self.w_quality.isChecked() if hasattr(self, "w_quality") else False,
            dependencies=self.w_deps.isChecked() if hasattr(self, "w_deps") else True,
            observability=self.w_obs.currentData() if hasattr(self, "w_obs") else "prometheus",
            iac=self.w_iac.currentData() if hasattr(self, "w_iac") else "opentofu",
            shared_host=self.w_shared.isChecked() if hasattr(self, "w_shared") else False,
        )

    def project(self) -> Project:
        return build_starter(self.collect(), self.catalog)
