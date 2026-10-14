# SPDX-License-Identifier: Apache-2.0
"""Dimensionnement des hôtes Docker : besoin calculé à partir des services Compose, type de machine proposé.

Le besoin d'un hôte est la somme des services du fichier Compose généré (application, bases, services de
plateforme), majorée d'une marge et multipliée par le nombre d'environnements que l'hôte porte (chacun lance son
propre projet Compose), plus le système et Docker. Les valeurs par service sont dans data/sizing.yaml.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from .catalog import DATA_DIR

COMPOSE_FILE = "deploy/docker-compose.yml"


@lru_cache(maxsize=1)
def table() -> dict:
    return yaml.safe_load((DATA_DIR / "sizing.yaml").read_text(encoding="utf-8"))


@dataclass
class ServiceNeed:
    name: str
    image: str
    cpu: int        # millièmes de vCPU
    memory: int     # Mio
    sourced: bool   # valeur tirée d'une documentation


@dataclass
class Capacity:
    type: str
    vcpu: float
    memory: float   # Gio


@dataclass
class HostNeed:
    key: str                     # groupe de machines (environnement ou hôte partagé)
    envs: list[str]              # environnements portés
    services: list[ServiceNeed] = field(default_factory=list)
    tool: str | None = None      # brique qui crée la machine (aws-ec2…), sinon hôte existant
    chosen: Capacity | None = None
    chosen_type: str = ""        # type saisi ou par défaut, même inconnu du tableau
    from_override: bool = False  # type venu d'une surcharge d'environnement

    @property
    def cpu(self) -> int:
        t = table()
        per_env = sum(s.cpu for s in self.services) * t["margin"]
        return math.ceil(per_env * len(self.envs) + t["system"]["cpu"])

    @property
    def memory(self) -> int:
        t = table()
        per_env = sum(s.memory for s in self.services) * t["margin"]
        return math.ceil(per_env * len(self.envs) + t["system"]["memory"])

    @property
    def vcpu(self) -> int:
        return max(1, math.ceil(self.cpu / 1000))

    @property
    def gib(self) -> float:
        return round(self.memory / 1024, 1)

    @property
    def undersized(self) -> bool:
        return self.chosen is not None and not fits(self.chosen, self)

    @property
    def suggestion(self) -> Capacity | None:
        return suggest(self.tool, self) if self.tool else None


def fits(cap: Capacity, need: HostNeed) -> bool:
    return cap.vcpu * 1000 >= need.cpu and cap.memory * 1024 >= need.memory


def service_need(name: str, image: str, app: str) -> ServiceNeed:
    t = table()
    if name == app or image.startswith("${IMAGE"):
        return ServiceNeed(name, image, t["app"]["cpu"], t["app"]["memory"], False)
    base = re.sub(r"(@sha256)?:[^:/]*$", "", image)
    prefix = max((p for p in t["services"] if base == p or base.startswith(p)), key=len, default=None)
    if prefix is None:
        return ServiceNeed(name, image, t["unknown"]["cpu"], t["unknown"]["memory"], False)
    spec = t["services"][prefix]
    return ServiceNeed(name, image, spec["cpu"], spec["memory"], bool(spec.get("source")))


def compose_needs(compose_text: str, app: str) -> list[ServiceNeed]:
    doc = yaml.safe_load(compose_text) or {}
    out = []
    for name, svc in (doc.get("services") or {}).items():
        if not isinstance(svc, dict) or str(svc.get("restart", "")) == "no" or svc.get("profiles"):
            continue  # tâche ponctuelle (migrations) ou service facultatif
        out.append(service_need(name, str(svc.get("image", "")), app))
    return out


def capacity(tool: str, type_: str) -> Capacity | None:
    t = table()
    for name, vcpu, mem in t["instances"].get(tool, []):
        if name == type_:
            return Capacity(name, vcpu, mem)
    known = t["known"].get(tool, {}).get(type_)
    if known:
        return Capacity(type_, known[0], known[1])
    if tool == "outscale-vm":  # tinavN.cXrYpZ : X vCPU, Y Gio
        m = re.fullmatch(r"tinav\d+\.c(\d+)r(\d+)p\d", type_)
        if m:
            return Capacity(type_, int(m.group(1)), int(m.group(2)))
    return None


def suggest(tool: str, need: HostNeed) -> Capacity | None:
    for name, vcpu, mem in table()["instances"].get(tool, []):
        cap = Capacity(name, vcpu, mem)
        if fits(cap, need):
            return cap
    return None


def host_needs(ir, files: dict[str, str]) -> list[HostNeed]:
    """Besoin de chaque groupe de machines ; vide sans fichier Compose ou hors hôte Docker / VM."""
    from .generators import hosts
    if ir.project.target not in ("docker-host", "vm") or COMPOSE_FILE not in files:
        return []
    services = compose_needs(files[COMPOSE_FILE], ir.app)
    tool = hosts.compute_tool(ir) if hosts.creates_hosts(ir) else None
    defaults = ir.catalog[tool].param_schema.get("instance_type") if tool else None
    out = []
    for g in hosts.groups(ir):
        need = HostNeed(g.key, [e.id for e in g.envs], services, tool)
        if tool:
            need.chosen_type = str(g.params.get("instance_type") or (defaults.default if defaults else "") or "")
            need.chosen = capacity(tool, need.chosen_type)
            need.from_override = any("instance_type" in e.overrides.get(tool, {}) for e in g.envs)
        out.append(need)
    return out
