# SPDX-License-Identifier: Apache-2.0
"""Création et modification d'une fiche personnelle (souvent à partir d'une entrée du Landscape)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import catalog_edit
from ..catalog import Catalog
from ..model import STAGES, Tool
from . import theme
from .widgets import icon, muted, plain

HOSTINGS = {"kubernetes": "Kubernetes", "docker-host": "Hôte Docker", "vm": "Machine virtuelle", "saas": "SaaS",
            "ci": "Dans la CI", "cli": "Poste ou CLI"}
LICENSES = ["unknown", "Apache-2.0", "MIT", "MPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-3.0", "LGPL-2.1",
            "BSD-3-Clause", "BSD-2-Clause", "EPL-2.0", "ISC", "BSL-1.1", "proprietary"]
LIFECYCLES = {"active": "Actif", "maintenance-ended": "Maintenance terminée", "archived": "Archivé",
              "discontinued": "Abandonné"}


def _csv(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


class _LicenseThread(QThread):
    found = Signal(object)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            self.found.emit(catalog_edit.license_from_repo(self.url))
        except Exception:  # réseau : on garde la saisie
            self.found.emit(None)


class FicheDialog(QDialog):
    """Formulaire d'une fiche ; contrôlée comme une fiche livrée avant d'être enregistrée."""

    def __init__(self, catalog: Catalog, data: dict[str, Any], editing: str | None = None,
                 source_entry: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.catalog, self.editing = catalog, editing
        self.saved_id: str | None = None
        self.source_entry = source_entry   # identifiant lsc-… remplacé par la nouvelle fiche
        self.worker: _LicenseThread | None = None
        self.extra: dict[str, Any] = {k: v for k, v in data.items() if k not in catalog_edit.FICHE_FIELDS}
        self.setWindowTitle("Modifier la fiche" if editing else "Nouvelle fiche personnelle")
        self.resize(760, 760)
        outer = QVBoxLayout(self)
        outer.addWidget(muted("La fiche rejoint votre catalogue personnel : les règles de compatibilité et les générateurs "
                              "s'en servent comme d'une fiche livrée. Relisez surtout les rôles, les capacités et les cibles."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.f_id = QLineEdit(data.get("id", ""))
        self.f_name = QLineEdit(data.get("name", ""))
        self.f_stage = QComboBox()
        for sid, label in STAGES:
            self.f_stage.addItem(label, sid)
        self.f_stage.setCurrentIndex(max(0, self.f_stage.findData(data.get("stage"))))
        extra_box = QWidget()
        grid = QGridLayout(extra_box)
        grid.setContentsMargins(0, 0, 0, 0)
        self.f_extra: dict[str, QCheckBox] = {}
        for i, (sid, label) in enumerate(STAGES):
            cb = QCheckBox(plain(label))
            cb.setChecked(sid in (data.get("extra_stages") or []))
            grid.addWidget(cb, i // 3, i % 3)
            self.f_extra[sid] = cb
        self.f_desc = QPlainTextEdit(data.get("description") or "")
        self.f_desc.setFixedHeight(70)
        self.f_home = QLineEdit(data.get("homepage") or "")
        self.f_repo = QLineEdit(data.get("repo") or "")
        lic_row = QHBoxLayout()
        self.f_license = QComboBox()
        self.f_license.setEditable(True)
        self.f_license.addItems(LICENSES)
        self.f_license.setCurrentText(data.get("license") or "unknown")
        self.lic_btn = QPushButton(icon("mdi6.cloud-search-outline"), "Lire sur le dépôt")
        self.lic_btn.setToolTip("Interroge GitHub ou GitLab.com pour connaître la licence du dépôt")
        self.lic_btn.clicked.connect(self._fetch_license)
        lic_row.addWidget(self.f_license, 1)
        lic_row.addWidget(self.lic_btn)
        host_box = QWidget()
        hl = QGridLayout(host_box)
        hl.setContentsMargins(0, 0, 0, 0)
        self.f_hosting: dict[str, QCheckBox] = {}
        for i, (key, label) in enumerate(HOSTINGS.items()):
            cb = QCheckBox(plain(label))
            cb.setChecked(key in (data.get("hosting") or []))
            hl.addWidget(cb, i // 3, i % 3)
            self.f_hosting[key] = cb
        known_roles = sorted({r for t in catalog.curated() for r in t.roles})
        known_caps = sorted({c for t in catalog.curated() for c in (*t.provides, *t.requires)})
        self.f_roles = QLineEdit(", ".join(data.get("roles") or []))
        self.f_roles.setPlaceholderText("ex. " + ", ".join(known_roles[:4]))
        self.f_roles.setToolTip("Rôles connus : " + ", ".join(known_roles))
        self.f_provides = QLineEdit(", ".join(data.get("provides") or []))
        self.f_requires = QLineEdit(", ".join(data.get("requires") or []))
        for w in (self.f_provides, self.f_requires):
            w.setToolTip("Capacités connues : " + ", ".join(known_caps))
        self.f_lifecycle = QComboBox()
        for k, v in LIFECYCLES.items():
            self.f_lifecycle.addItem(v, k)
        self.f_lifecycle.setCurrentIndex(max(0, self.f_lifecycle.findData(data.get("lifecycle", "active"))))
        self.f_note = QLineEdit(data.get("lifecycle_note") or "")
        self.f_replacements = QLineEdit(", ".join(data.get("replacements") or []))
        self.f_replacements.setPlaceholderText("identifiants de fiches, ex. buildkit, buildah")
        self.f_dev_only = QCheckBox("Réservé au développement (refusé pour la production)")
        self.f_dev_only.setChecked(bool(data.get("dev_only")))
        self.landscape_name = data.get("landscape_name")
        self.verified = data.get("verified")
        rows = [("Identifiant", self.f_id), ("Nom", self.f_name), ("Étape principale", self.f_stage),
                ("Autres étapes", extra_box), ("Description", self.f_desc), ("Site", self.f_home),
                ("Dépôt source", self.f_repo), ("Licence", lic_row), ("S'exécute sur", host_box),
                ("Rôles", self.f_roles), ("Fournit", self.f_provides), ("Requiert", self.f_requires),
                ("Cycle de vie", self.f_lifecycle), ("Note de cycle de vie", self.f_note),
                ("Remplaçants", self.f_replacements), ("", self.f_dev_only)]
        for label, w in rows:
            if isinstance(w, QWidget):
                w.setAccessibleName(label or "Développement uniquement")
            form.addRow(label, w)
        if self.landscape_name:
            form.addRow("Landscape", muted(f"lié à l'entrée « {self.landscape_name} »"))
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet(f"color: {theme.current().blocking};")
        outer.addWidget(self.problems)
        row = QHBoxLayout()
        row.addStretch(1)
        self.save_btn = QPushButton(icon("mdi6.content-save-outline"), "Enregistrer la fiche")
        self.save_btn.setProperty("class", "success")
        self.save_btn.clicked.connect(self.save)
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        row.addWidget(self.save_btn)
        row.addWidget(cancel)
        outer.addLayout(row)
        for w in (self.f_id, self.f_name, self.f_home, self.f_repo, self.f_roles, self.f_provides, self.f_requires,
                  self.f_note, self.f_replacements):
            w.textChanged.connect(self._check)
        self.f_license.currentTextChanged.connect(self._check)
        for c in (self.f_stage, self.f_lifecycle):
            c.currentIndexChanged.connect(self._check)
        for cb in (*self.f_extra.values(), *self.f_hosting.values()):
            cb.toggled.connect(self._check)
        self._check()

    def data(self) -> dict[str, Any]:
        stage = self.f_stage.currentData()
        out: dict[str, Any] = dict(self.extra)
        out.update({
            "id": self.f_id.text().strip(), "name": self.f_name.text().strip(), "stage": stage,
            "extra_stages": [s for s, cb in self.f_extra.items() if cb.isChecked() and s != stage],
            "roles": _csv(self.f_roles.text()), "description": self.f_desc.toPlainText().strip(),
            "homepage": self.f_home.text().strip() or None, "license": self.f_license.currentText().strip() or "unknown",
            "repo": self.f_repo.text().strip() or None,
            "hosting": [h for h, cb in self.f_hosting.items() if cb.isChecked()],
            "provides": _csv(self.f_provides.text()), "requires": _csv(self.f_requires.text()),
            "lifecycle": self.f_lifecycle.currentData(), "lifecycle_note": self.f_note.text().strip(),
            "replacements": _csv(self.f_replacements.text()), "dev_only": self.f_dev_only.isChecked(),
            "landscape_name": self.landscape_name, "verified": self.verified,
        })
        if not out["hosting"]:
            out.pop("hosting")
        return out

    def _check(self) -> list[str]:
        tool, problems = catalog_edit.validate_fiche(self.data(), self.catalog, self.editing)
        if not problems and tool is not None:
            problems = self._advice(tool)
            self.problems.setStyleSheet(f"color: {theme.current().warning};")
            self.save_btn.setEnabled(True)
        else:
            self.problems.setStyleSheet(f"color: {theme.current().blocking};")
            self.save_btn.setEnabled(False)
        self.problems.setText("\n".join(f"• {p}" for p in problems))
        return problems

    @staticmethod
    def _advice(tool: Tool) -> list[str]:
        tips = []
        if tool.lifecycle != "active":
            tips.append(f"Cycle de vie « {LIFECYCLES[tool.lifecycle]} » : les projets qui utilisent la brique "
                        "recevront un avertissement." + (f" ({tool.lifecycle_note})" if tool.lifecycle_note else ""))
        if tool.license == "unknown":
            tips.append("Licence inconnue : la brique sera écartée par la politique « open source uniquement ».")
        if not tool.roles:
            tips.append("Aucun rôle : les règles d'exclusivité (deux CI, deux registres…) ne s'appliqueront pas.")
        return tips

    def _fetch_license(self) -> None:
        url = self.f_repo.text().strip()
        if not url or self.worker is not None:
            return
        self.lic_btn.setEnabled(False)
        self.lic_btn.setText("Lecture…")
        self.worker = _LicenseThread(url)
        self.worker.found.connect(self._license_found)
        self.worker.finished.connect(self._license_over)
        self.worker.start()

    def _license_found(self, value: str | None) -> None:
        if value:
            self.f_license.setCurrentText(value)
            self.lic_btn.setToolTip(f"Licence lue sur le dépôt : {value}")
        else:
            self.lic_btn.setToolTip("Licence introuvable (dépôt non pris en charge, réseau ou limite d'API)")

    def _license_over(self) -> None:
        self.worker = None
        self.lic_btn.setEnabled(True)
        self.lic_btn.setText("Lire sur le dépôt")

    def save(self) -> None:
        self._check()
        if not self.save_btn.isEnabled():
            return
        try:
            catalog_edit.save_fiche(self.data(), self.catalog, editing=self.editing)
        except ValueError as exc:
            self.problems.setText(str(exc))
            return
        self.saved_id = self.f_id.text().strip()
        self.accept()

    def done(self, r: int) -> None:
        if self.worker is not None:
            self.worker.wait(25000)
        super().done(r)


def open_fiche_dialog(parent: QWidget, catalog: Catalog, tool: Tool) -> FicheDialog:
    """Dialogue adapté : création depuis une entrée du Landscape, ou modification d'une fiche personnelle."""
    if tool.curated and tool.origin == "utilisateur":
        return FicheDialog(catalog, catalog_edit.tool_to_data(tool), editing=tool.id, parent=parent)
    entry = catalog.landscape_entry_for(tool) or {"name": tool.name, "description": tool.description,
                                                  "homepage_url": tool.homepage,
                                                  "repo_url": tool.landscape.repo_url if tool.landscape else None,
                                                  "subcategory": tool.landscape.subcategory if tool.landscape else None}
    dlg = FicheDialog(catalog, catalog_edit.draft_from_landscape(entry, catalog), source_entry=tool.id, parent=parent)
    dlg.setWindowTitle(f"Créer une fiche pour « {tool.name} »")
    return dlg

