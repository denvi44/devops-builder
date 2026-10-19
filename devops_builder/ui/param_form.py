# SPDX-License-Identifier: Apache-2.0
"""Formulaire typé des paramètres d'une brique (à partir du schéma de la fiche)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..model import BrickInstance, Environment, ParamSpec, Project, Tool
from ..params import check_value, effective_params, resolve_default
from . import theme
from .widgets import icon, muted, section_title


class ParamForm(QWidget):
    """Émet `changed(params)` quand une valeur est validée (fin de saisie, choix, case)."""

    changed = Signal(dict)

    def __init__(self, tool: Tool, brick: BrickInstance, project: Project | None, env: Environment | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.tool, self.brick, self.project, self.env = tool, brick, project, env
        # Mode brique : valeurs communes ; mode environnement : surcharges de cet environnement.
        self.source: dict[str, Any] = dict(env.overrides.get(brick.service_id, {}) if env else brick.params)
        self.editors: dict[str, QWidget] = {}
        self.errors: dict[str, QLabel] = {}
        self.unknown: dict[str, Any] = {k: v for k, v in self.source.items() if k not in tool.param_schema}
        self.inherited: dict[str, Any] = {}
        if env is not None:
            bare = env.model_copy(update={"overrides": {k: v for k, v in env.overrides.items() if k != brick.service_id}})
            self.inherited = effective_params(tool, brick, project, bare)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(4)
        for key, spec in tool.param_schema.items():
            if not spec.applies_to(project) and key not in self.source:
                continue  # sans effet pour cette cible d'hébergement
            editor = self._editor(key, spec, self.source.get(key))
            label = QLabel(spec.label + (" *" if spec.required else ""))
            label.setBuddy(editor)
            if spec.description:
                label.setToolTip(spec.description)
                editor.setToolTip(spec.description)
            editor.setAccessibleName(spec.label)
            editor.setAccessibleDescription(spec.description or spec.pattern_hint)
            if not isinstance(editor, QCheckBox):
                editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            err = QLabel()
            err.setWordWrap(True)
            err.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            err.setStyleSheet(f"color: {theme.current().blocking};")
            err.hide()
            box = QWidget()
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            col = QVBoxLayout(box)
            col.setContentsMargins(0, 0, 0, 6)
            col.setSpacing(2)
            col.addWidget(editor)
            col.addWidget(err)
            form.addRow(label, box)
            self.editors[key] = editor
            self.errors[key] = err
            self._validate(key)
        lay.addLayout(form)
        if any(s.required for s in tool.param_schema.values()) and env is None:
            lay.addWidget(muted("* à renseigner ; sinon la valeur d'exemple est écrite et signalée."))
        if self.unknown:
            lay.addWidget(section_title("Paramètres inconnus"))
            self.unknown_rows: dict[str, QWidget] = {}
            for key, value in self.unknown.items():
                row_w = QWidget()
                row = QHBoxLayout(row_w)
                row.setContentsMargins(0, 0, 0, 0)
                lbl = QLabel(f"{key} = {value}")
                lbl.setStyleSheet(f"color: {theme.current().warning};")
                row.addWidget(lbl, 1)
                rm = QPushButton(icon("mdi6.close"), "Supprimer")
                rm.setAccessibleName(f"Supprimer le paramètre {key}")
                rm.clicked.connect(lambda checked=False, k=key: self._drop_unknown(k))
                row.addWidget(rm)
                lay.addWidget(row_w)
                self.unknown_rows[key] = row_w

    # ---------------------------------------------------------------- éditeurs
    def _hint(self, key: str, spec: ParamSpec) -> str:
        if self.env is not None:
            value = self.inherited.get(key)
            return f"{value} (hérité)" if value not in (None, "") else ""
        default = resolve_default(spec, self.project)
        if default is not None:
            return f"{default} (défaut)"
        if spec.example:
            return f"ex. {spec.example}"
        return ""

    def _editor(self, key: str, spec: ParamSpec, value: Any) -> QWidget:
        if spec.type == "bool":
            cb = QCheckBox()
            default = resolve_default(spec, self.project)
            cb.setChecked(bool(value if value is not None else default))
            cb.toggled.connect(lambda _=False: self._commit())
            return cb
        if spec.choices or spec.suggestions:
            combo = QComboBox()
            combo.setEditable(not spec.choices)
            combo.addItem("")
            combo.addItems(spec.choices or spec.suggestions)
            # Valeur initiale d'abord, signaux ensuite : l'éditeur n'est pas encore enregistré.
            if combo.isEditable():
                combo.lineEdit().setPlaceholderText(self._hint(key, spec))
            else:
                combo.setItemText(0, self._hint(key, spec) or "(par défaut)")
            combo.setCurrentText("" if value is None else str(value))
            if not combo.isEditable() and value is None:
                combo.setCurrentIndex(0)
            if combo.isEditable():
                combo.lineEdit().textChanged.connect(lambda _t, k=key: self._validate(k))
                combo.lineEdit().editingFinished.connect(self._commit)
            combo.activated.connect(lambda _i, k=key: (self._validate(k), self._commit()))
            return combo
        line = QLineEdit("" if value is None else str(value))
        line.setPlaceholderText(self._hint(key, spec))
        line.setClearButtonEnabled(True)
        line.textChanged.connect(lambda _t, k=key: self._validate(k))
        line.editingFinished.connect(self._commit)
        return line

    def _raw(self, key: str) -> Any:
        w = self.editors[key]
        spec = self.tool.param_schema[key]
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QComboBox):
            if not w.isEditable() and w.currentIndex() == 0:
                return None
            text = w.currentText().strip()
        else:
            text = w.text().strip()  # type: ignore[attr-defined]
        if text == "":
            return None
        if spec.type == "int":
            try:
                return int(text)
            except ValueError:
                return text
        return text

    def _validate(self, key: str) -> bool:
        value = self._raw(key)
        err = None if value is None else check_value(self.tool.param_schema[key], value)
        label = self.errors[key]
        label.setText(err or "")
        label.setVisible(bool(err))
        return err is None

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, spec in self.tool.param_schema.items():
            if key not in self.editors:
                continue  # paramètre sans effet pour cette cible : pas de champ
            value = self._raw(key)
            if value is None:
                continue
            reference = self.inherited.get(key) if self.env is not None else resolve_default(spec, self.project)
            if spec.type == "bool" and value == bool(reference):
                continue  # identique à la valeur de référence : inutile de le stocker
            out[key] = value
        out.update(self.unknown)
        return out

    def _commit(self) -> None:
        params = self.values()
        if params != self.source:
            self.source = dict(params)
            self.changed.emit(params)

    def _drop_unknown(self, key: str) -> None:
        self.unknown.pop(key, None)
        row = getattr(self, "unknown_rows", {}).get(key)
        if row is not None:
            row.hide()
        self._commit()
