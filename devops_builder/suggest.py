"""Suggestions de briques complémentaires pour la brique sélectionnée."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .catalog import DATA_DIR, Catalog
from .model import Project, Tool

SUGGESTIONS_FILE = DATA_DIR / "suggestions.yaml"


@lru_cache(maxsize=1)
def _table(path: Path = SUGGESTIONS_FILE) -> dict[str, list[str]]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def check_table(catalog: Catalog) -> list[str]:
    """Identifiants inconnus dans suggestions.yaml (contrôlé par les tests)."""
    errors = []
    for src, targets in _table().items():
        for tid in [src, *targets]:
            if tid not in catalog:
                errors.append(f"{src} → {tid}")
    return errors


def placeable(tool: Tool, project: Project, catalog: Catalog) -> bool:
    """La brique peut-elle tourner sur la cible du projet sans ajouter de cluster ?"""
    if not tool.kubernetes_only or project.target in ("kubernetes", "kubernetes-managed"):
        return True
    return any("kubernetes-cluster" in t.roles for tid in project.tool_ids() if (t := catalog.get(tid)))


def suggestions(project: Project, catalog: Catalog, tool_id: str, limit: int = 4) -> list[Tool]:
    present = project.tool_ids()
    out: list[Tool] = []
    for tid in _table().get(tool_id, []):
        tool = catalog.get(tid)
        if tool is None or tid in present or not placeable(tool, project, catalog):
            continue
        if project.license_policy == "oss-only" and not tool.is_oss:
            continue
        out.append(tool)
    return out[:limit]
