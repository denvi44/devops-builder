# SPDX-License-Identifier: Apache-2.0
"""Plusieurs instances d'un même outil dans un pipeline (deux Grafana, deux Gitea…).

Chaque brique porte un nom d'instance facultatif ; l'instance principale (nom vide) garde l'identifiant de
l'outil, les autres reçoivent « <outil>-<nom> » comme identifiant de service Compose, de release Helm et de
surcharge d'environnement. Seuls les outils marqués `multi` dans le catalogue acceptent plusieurs instances.
"""

from __future__ import annotations

import re

from .model import BrickInstance, Project, Tool

NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
HOST_PORT_STEP = 100   # décalage des ports publiés par rang d'instance (sans Traefik)


def rank(project: Project, brick: BrickInstance) -> int:
    """Rang de la brique parmi celles du même outil (0 : la première)."""
    return [b.uid for b in project.bricks_for(brick.tool)].index(brick.uid)


def label(tool: Tool | None, brick: BrickInstance) -> str:
    name = tool.name if tool else brick.tool
    return f"{name} ({brick.instance})" if brick.instance else name


def suggest_name(project: Project, tool_id: str) -> str:
    """Premier nom libre : « 2 », « 3 »… (l'instance principale n'a pas de nom)."""
    taken = {b.service_id for b in project.bricks_for(tool_id)}
    n = 2
    while f"{tool_id}-{n}" in taken:
        n += 1
    return str(n)


def check_name(name: str) -> str | None:
    """Message d'erreur si le nom ne convient pas à un identifiant de service, sinon None."""
    if name and not NAME.match(name):
        return "lettres minuscules, chiffres et tirets (pas au début ni à la fin)"
    if len(name) > 30:
        return "30 caractères au plus"
    return None


def duplicates(project: Project) -> dict[str, list[BrickInstance]]:
    """Briques qui partagent le même identifiant de service."""
    seen: dict[str, list[BrickInstance]] = {}
    for _, b in project.all_bricks():
        seen.setdefault(b.service_id, []).append(b)
    return {sid: bricks for sid, bricks in seen.items() if len(bricks) > 1}


def chart_namespace(tool_id: str, brick: BrickInstance) -> str:
    """Espace de noms Kubernetes de l'instance : celui du chart, suffixé du nom pour une instance nommée."""
    from .generators.platform import PLATFORM_CHARTS
    ns = PLATFORM_CHARTS[tool_id].namespace
    return f"{ns}-{brick.instance}" if brick.instance else ns
