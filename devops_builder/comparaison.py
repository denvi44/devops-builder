# SPDX-License-Identifier: Apache-2.0
"""Comparaison avant / après de deux architectures : ce qui change quand on modifie un projet.

La comparaison porte sur le projet lui-même (réglages, environnements, briques et leurs paramètres), sur ce que
les règles en disent (diagnostics apparus ou résolus), sur les ports publiés et sur les fichiers générés.
Elle ne modifie rien : elle lit deux projets et rend un rapport, en Markdown ou en dictionnaire (JSON).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from .catalog import Catalog
from .model import ENVIRONMENTS, STAGE_LABELS, TARGETS, Project, Severity
from .rules import Diagnostic, RuleEngine

# Fichiers qui décrivent le résultat plutôt que l'architecture : leurs différences n'apprennent rien de plus
_IGNORED_FILES = {"devops-builder.yaml"}


@dataclass
class BrickChange:
    stage: str
    tool: str
    name: str
    kind: str                       # ajoutée | retirée | déplacée | modifiée
    detail: list[str] = field(default_factory=list)


@dataclass
class FileChange:
    path: str
    kind: str                       # ajouté | retiré | modifié
    added: int = 0
    removed: int = 0


@dataclass
class Comparison:
    before: str
    after: str
    settings: list[str] = field(default_factory=list)
    environments: list[str] = field(default_factory=list)
    bricks: list[BrickChange] = field(default_factory=list)
    new_diagnostics: list[Diagnostic] = field(default_factory=list)
    resolved_diagnostics: list[Diagnostic] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)
    files: list[FileChange] = field(default_factory=list)
    files_compared: bool = False
    before_blocking: int = 0
    after_blocking: int = 0

    @property
    def identical(self) -> bool:
        return not (self.settings or self.environments or self.bricks or self.new_diagnostics
                    or self.resolved_diagnostics or self.ports or self.files)

    @property
    def introduces_blocking(self) -> bool:
        return any(d.severity is Severity.BLOCKING for d in self.new_diagnostics)

    def to_dict(self) -> dict[str, Any]:
        def diag(d: Diagnostic) -> dict[str, Any]:
            return {"rule": d.rule_id, "severity": d.severity.value, "message": d.message}
        return {
            "before": self.before, "after": self.after, "identical": self.identical,
            "settings": self.settings, "environments": self.environments,
            "bricks": [{"stage": b.stage, "tool": b.tool, "name": b.name, "change": b.kind, "detail": b.detail}
                       for b in self.bricks],
            "new_diagnostics": [diag(d) for d in self.new_diagnostics],
            "resolved_diagnostics": [diag(d) for d in self.resolved_diagnostics],
            "blocking": {"before": self.before_blocking, "after": self.after_blocking},
            "ports": self.ports,
            "files": [{"path": f.path, "change": f.kind, "added": f.added, "removed": f.removed} for f in self.files]
            if self.files_compared else None,
        }

    def summary(self) -> str:
        if self.identical:
            return "Aucune différence."
        parts = []
        counts = {k: sum(1 for b in self.bricks if b.kind == k) for k in ("ajoutée", "retirée", "déplacée", "modifiée")}
        for kind, n in counts.items():
            if n:
                parts.append(f"{n} brique{'s' if n > 1 else ''} {kind}{'s' if n > 1 else ''}")
        if self.settings or self.environments:
            parts.append(f"{len(self.settings) + len(self.environments)} réglage(s) du projet")
        if self.new_diagnostics:
            parts.append(f"{len(self.new_diagnostics)} diagnostic(s) nouveau(x)")
        if self.resolved_diagnostics:
            parts.append(f"{len(self.resolved_diagnostics)} résolu(s)")
        if self.files_compared and self.files:
            parts.append(f"{len(self.files)} fichier(s) généré(s) différent(s)")
        return ", ".join(parts) + "."

    def to_markdown(self) -> str:
        out = [f"# Comparaison : {self.before} → {self.after}", "", self.summary(), ""]
        if self.identical:
            return "\n".join(out) + "\n"
        if self.settings or self.environments:
            out += ["## Réglages du projet", "", *[f"- {s}" for s in [*self.settings, *self.environments]], ""]
        if self.bricks:
            out += ["## Briques", ""]
            for b in self.bricks:
                where = STAGE_LABELS.get(b.stage, b.stage)
                out.append(f"- **{b.name}** ({where}) : {b.kind}" + (f" — {' ; '.join(b.detail)}" if b.detail else ""))
            out.append("")
        out += ["## Diagnostics", "",
                f"Erreurs bloquantes : {self.before_blocking} avant, {self.after_blocking} après.", ""]
        if self.new_diagnostics:
            out += ["Nouveaux :", "", *[f"- {d.severity.label} {d.rule_id} : {d.message}" for d in self.new_diagnostics], ""]
        if self.resolved_diagnostics:
            out += ["Résolus :", "", *[f"- {d.severity.label} {d.rule_id} : {d.message}" for d in self.resolved_diagnostics], ""]
        if not (self.new_diagnostics or self.resolved_diagnostics):
            out += ["Aucun diagnostic ne change.", ""]
        if self.ports:
            out += ["## Ports publiés", "", *[f"- {p}" for p in self.ports], ""]
        if self.files_compared:
            out += ["## Fichiers générés", ""]
            if self.files:
                out += ["| Fichier | Changement | Lignes |", "|---|---|---|"]
                out += [f"| `{f.path}` | {f.kind} | +{f.added} −{f.removed} |" for f in self.files]
            else:
                out.append("Les fichiers générés sont identiques.")
            out.append("")
        return "\n".join(out)


# ------------------------------------------------------------------ comparaison
def _label(catalog: Catalog, tool: str, instance: str = "") -> str:
    t = catalog.get(tool)
    name = t.name if t else tool
    return f"{name} ({instance})" if instance else name


def _bricks(project: Project) -> dict[str, tuple[str, Any]]:
    return {b.service_id: (stage, b) for stage, b in project.all_bricks()}


def _params_diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    out = []
    for key in sorted({*before, *after}):
        if before.get(key) != after.get(key):
            out.append(f"{key} : {_show(before.get(key))} → {_show(after.get(key))}")
    return out


def _show(value: Any) -> str:
    if isinstance(value, bool):
        return "oui" if value else "non"
    return "(vide)" if value in (None, "") else str(value)


def _settings(before: Project, after: Project) -> list[str]:
    out = []
    if before.target != after.target:
        out.append(f"Cible d'hébergement : {TARGETS.get(before.target, before.target)} → "
                   f"{TARGETS.get(after.target, after.target)}")
    for label, a, b in (
        ("Nom", before.name, after.name),
        ("Application", "avec" if before.app.enabled else "sans (plateforme seule)",
         "avec" if after.app.enabled else "sans (plateforme seule)"),
        ("Langage", before.app.language, after.app.language), ("Port de l'application", before.app.port, after.app.port),
        ("Image", before.app.image_name, after.app.image_name),
        ("SecNumCloud", "oui" if before.secnumcloud else "non", "oui" if after.secnumcloud else "non"),
        ("Authentification cloud", before.cloud_auth, after.cloud_auth),
        ("Licences", before.license_policy, after.license_policy),
    ):
        if a != b:
            out.append(f"{label} : {a} → {b}")
    return out


def _environments(before: Project, after: Project) -> list[str]:
    old = {e.id: e for e in before.environments}
    new = {e.id: e for e in after.environments}
    out = []
    for env_id in new.keys() - old.keys():
        out.append(f"Environnement ajouté : {new[env_id].display} ({env_id})")
    for env_id in old.keys() - new.keys():
        out.append(f"Environnement retiré : {old[env_id].display} ({env_id})")
    for env_id in old.keys() & new.keys():
        a, b = old[env_id], new[env_id]
        for label, x, y in (("type", ENVIRONMENTS.get(a.kind, a.kind), ENVIRONMENTS.get(b.kind, b.kind)),
                            ("approbation", _show(a.approval), _show(b.approval)), ("hôte", a.host or "—", b.host or "—"),
                            ("cluster", a.cluster or "—", b.cluster or "—")):
            if x != y:
                out.append(f"Environnement {env_id} — {label} : {x} → {y}")
        for tool in sorted({*a.overrides, *b.overrides}):
            for d in _params_diff(a.overrides.get(tool, {}), b.overrides.get(tool, {})):
                out.append(f"Environnement {env_id} — {tool} : {d}")
    return out


def _diag_key(d: Diagnostic) -> tuple[str, str]:
    return d.rule_id, d.message


def _port_lines(project: Project, catalog: Catalog) -> dict[tuple[str, str, int], str]:
    from .ports import port_plan
    out = {}
    for e in port_plan(project, catalog):
        if e.host_port is None:
            continue
        out[(e.env_id, e.component_id, e.container_port)] = f"{e.env} — {e.component} : {e.host_port}"
    return out


def _ports(before: Project, after: Project, catalog: Catalog) -> list[str]:
    old, new = _port_lines(before, catalog), _port_lines(after, catalog)
    out = []
    for key in sorted(new.keys() - old.keys()):
        out.append(f"ajouté — {new[key]}")
    for key in sorted(old.keys() - new.keys()):
        out.append(f"retiré — {old[key]}")
    for key in sorted(old.keys() & new.keys()):
        if old[key] != new[key]:
            out.append(f"changé — {old[key]} → {new[key].rsplit(' : ', 1)[-1]}")
    return out


def _file_changes(before_files: dict[str, str], after_files: dict[str, str]) -> list[FileChange]:
    out = []
    for path in sorted(before_files.keys() | after_files.keys()):
        if path in _IGNORED_FILES:
            continue
        a, b = before_files.get(path), after_files.get(path)
        if a == b:
            continue
        if a is None:
            out.append(FileChange(path, "ajouté", added=len(b.splitlines())))
        elif b is None:
            out.append(FileChange(path, "retiré", removed=len(a.splitlines())))
        else:
            added = removed = 0
            for line in difflib.ndiff(a.splitlines(), b.splitlines()):
                if line.startswith("+ "):
                    added += 1
                elif line.startswith("- "):
                    removed += 1
            out.append(FileChange(path, "modifié", added=added, removed=removed))
    return out


def compare(before: Project, after: Project, catalog: Catalog, engine: RuleEngine | None = None,
            files: bool = True) -> Comparison:
    """Rapport des différences entre deux projets ; `files` génère aussi les fichiers des deux côtés."""
    engine = engine or RuleEngine(catalog)
    cmp = Comparison(before=before.name, after=after.name)
    cmp.settings = _settings(before, after)
    cmp.environments = _environments(before, after)

    old, new = _bricks(before), _bricks(after)
    for sid in new.keys() - old.keys():
        stage, b = new[sid]
        cmp.bricks.append(BrickChange(stage, b.tool, _label(catalog, b.tool, b.instance), "ajoutée"))
    for sid in old.keys() - new.keys():
        stage, b = old[sid]
        cmp.bricks.append(BrickChange(stage, b.tool, _label(catalog, b.tool, b.instance), "retirée"))
    for sid in old.keys() & new.keys():
        (s1, b1), (s2, b2) = old[sid], new[sid]
        name = _label(catalog, b2.tool, b2.instance)
        if s1 != s2:
            cmp.bricks.append(BrickChange(s2, b2.tool, name, "déplacée",
                                          [f"{STAGE_LABELS.get(s1, s1)} → {STAGE_LABELS.get(s2, s2)}"]))
        detail = _params_diff(b1.params, b2.params)
        if detail:
            cmp.bricks.append(BrickChange(s2, b2.tool, name, "modifiée", detail))
    order = {"ajoutée": 0, "retirée": 1, "déplacée": 2, "modifiée": 3}
    stages = list(STAGE_LABELS)
    cmp.bricks.sort(key=lambda b: (stages.index(b.stage) if b.stage in stages else 99, order[b.kind], b.name))

    d_before, d_after = engine.evaluate(before), engine.evaluate(after)
    keys_before, keys_after = {_diag_key(d) for d in d_before}, {_diag_key(d) for d in d_after}
    cmp.new_diagnostics = sorted((d for d in d_after if _diag_key(d) not in keys_before), key=lambda d: d.severity.rank)
    cmp.resolved_diagnostics = sorted((d for d in d_before if _diag_key(d) not in keys_after), key=lambda d: d.severity.rank)
    cmp.before_blocking = len(RuleEngine.blocking(d_before))
    cmp.after_blocking = len(RuleEngine.blocking(d_after))
    cmp.ports = _ports(before, after, catalog)

    if files:
        from .generators import generate
        cmp.files_compared = True
        cmp.files = _file_changes(generate(before, catalog, engine, allow_blocking=True).files,
                                  generate(after, catalog, engine, allow_blocking=True).files)
    return cmp
