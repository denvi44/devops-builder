# SPDX-License-Identifier: Apache-2.0
"""Validation et résolution des paramètres de briques."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from .model import BrickInstance, Environment, ParamSpec, Project, Tool


@dataclass
class ParamIssue:
    key: str
    kind: str  # invalid | unknown | example | missing
    message: str
    suggestion: str | None = None  # clé proche pour une clé inconnue


def _app_name(value: Any, project: Project | None) -> Any:
    if isinstance(value, str) and project is not None:
        return value.replace("{app}", project.app.image_name or "app")
    return value


def resolve_default(spec: ParamSpec, project: Project | None) -> Any:
    return _app_name(spec.default, project)


def resolve_example(spec: ParamSpec, project: Project | None) -> Any:
    """Valeur d'exemple, « {app} » remplacé par le nom de l'image du projet."""
    return _app_name(spec.example, project)


def effective_params(tool: Tool, brick: BrickInstance | None, project: Project | None,
                     env: Environment | None = None) -> dict[str, Any]:
    """Valeurs utilisées à la génération.

    Ordre : surcharge de l'environnement > saisie de la brique > défaut > valeur d'exemple.
    Un paramètre « par environnement » sans surcharge reçoit le suffixe de l'environnement.
    """
    out: dict[str, Any] = dict(tool.params)
    for key, spec in tool.param_schema.items():
        default = resolve_default(spec, project)
        if default is not None:
            out[key] = default
        elif spec.example is not None:
            out[key] = resolve_example(spec, project)
    if brick is not None:
        for key, value in brick.params.items():
            if value not in (None, ""):
                out[key] = value
    if env is not None and project is not None:
        overrides = env.overrides.get(tool.id, {})
        for key, spec in tool.param_schema.items():
            if spec.per_env and key not in overrides and isinstance(out.get(key), str):
                out[key] = out[key] + project.env_suffix(env)
        for key, value in overrides.items():
            if value not in (None, ""):
                out[key] = value
    return out


def check_value(spec: ParamSpec, value: Any) -> str | None:
    """Message d'erreur si la valeur ne respecte pas le schéma, sinon None."""
    if spec.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            try:
                int(str(value))
            except ValueError:
                return "doit être un nombre entier"
        return None
    if spec.type == "bool":
        if not isinstance(value, bool):
            return "doit valoir true ou false"
        return None
    text = str(value)
    if spec.choices and text not in spec.choices:
        return "doit être l'une des valeurs : " + ", ".join(spec.choices)
    if spec.max_length is not None and len(text) > spec.max_length:
        return f"dépasse {spec.max_length} caractères"
    if spec.pattern and not re.fullmatch(spec.pattern, text):
        return "format attendu : " + (spec.pattern_hint or spec.pattern)
    return None


def check_brick(tool: Tool, brick: BrickInstance, project: Project | None) -> list[ParamIssue]:
    if not tool.param_schema:
        return []
    issues: list[ParamIssue] = []
    known = list(tool.param_schema)
    for key, value in brick.params.items():
        spec = tool.param_schema.get(key)
        if spec is None:
            close = difflib.get_close_matches(key, known, n=1, cutoff=0.6)
            issues.append(ParamIssue(key, "unknown", f"paramètre inconnu « {key} », ignoré à la génération",
                                     close[0] if close else None))
            continue
        if value in (None, ""):
            continue
        err = check_value(spec, value)
        if err:
            issues.append(ParamIssue(key, "invalid", f"« {spec.label} » vaut « {value} » ; {err}"))
    for key, spec in tool.param_schema.items():
        given = brick.params.get(key)
        if given not in (None, ""):
            continue
        default = resolve_default(spec, project)
        if default is not None:
            err = check_value(spec, default)
            if err:  # défaut dérivé du projet (ex. nom d'image) incompatible
                issues.append(ParamIssue(key, "invalid", f"« {spec.label} » vaut « {default} » (déduit du projet) ; {err}"))
            continue
        if spec.required and spec.example is not None:
            issues.append(ParamIssue(key, "example",
                                     f"« {spec.label} » non renseigné : la valeur d'exemple « {resolve_example(spec, project)} » "
                                     "sera écrite dans les fichiers"))
        elif spec.required:
            issues.append(ParamIssue(key, "missing", f"« {spec.label} » est obligatoire"))
    return issues


def check_overrides(tool: Tool, env: Environment) -> list[ParamIssue]:
    """Contrôle les surcharges d'un environnement pour une brique."""
    overrides = env.overrides.get(tool.id, {})
    issues: list[ParamIssue] = []
    known = list(tool.param_schema)
    where = f"environnement « {env.display} »"
    for key, value in overrides.items():
        spec = tool.param_schema.get(key)
        if spec is None:
            close = difflib.get_close_matches(key, known, n=1, cutoff=0.6)
            issues.append(ParamIssue(key, "unknown", f"paramètre inconnu « {key} » ({where}), ignoré à la génération",
                                     close[0] if close else None))
            continue
        if value in (None, ""):
            continue
        err = check_value(spec, value)
        if err:
            issues.append(ParamIssue(key, "invalid", f"« {spec.label} » vaut « {value} » ({where}) ; {err}"))
    return issues
