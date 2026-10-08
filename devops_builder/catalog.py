"""Chargement du catalogue : fiches curées + index brut du CNCF Landscape."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .model import STAGE_IDS, LandscapeRef, Tool

DATA_DIR = Path(__file__).parent / "data"

# Correspondance sous-catégorie Landscape → étape du pipeline, pour les
# entrées non curées (affichées « non vérifiées » dans la palette).
SUBCATEGORY_STAGE = {
    "Automation & Configuration": "infrastructure",
    "Container Registry": "artifacts",
    "Security & Compliance": "security",
    "Key Management": "platform",
    "Cloud Native Storage": "platform",
    "Container Runtime": "platform",
    "Cloud Native Network": "platform",
    "Scheduling & Orchestration": "platform",
    "Coordination & Service Discovery": "platform",
    "Remote Procedure Call": "platform",
    "Service Proxy": "platform",
    "API Gateway": "platform",
    "Service Mesh": "platform",
    "Database": "platform",
    "Streaming & Messaging": "platform",
    "Application Definition & Image Build": "build",
    "Continuous Integration & Delivery": "build",
    "Certified Kubernetes - Distribution": "infrastructure",
    "Certified Kubernetes - Hosted": "infrastructure",
    "Certified Kubernetes - Installer": "infrastructure",
    "PaaS/Container Service": "deploy",
    "Feature Flagging": "deploy",
    "Chaos Engineering": "test",
    "Continuous Optimization": "observability",
    "Observability": "observability",
}


@dataclass
class Catalog:
    tools: dict[str, Tool] = field(default_factory=dict)

    # ----------------------------------------------------------------- access
    def get(self, tool_id: str) -> Tool | None:
        return self.tools.get(tool_id)

    def __getitem__(self, tool_id: str) -> Tool:
        return self.tools[tool_id]

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self.tools

    def curated(self) -> list[Tool]:
        return [t for t in self.tools.values() if t.curated]

    def providing(self, capability: str) -> list[Tool]:
        return [t for t in self.tools.values() if capability in t.provides and t.curated]

    def with_role(self, role: str) -> list[Tool]:
        return [t for t in self.tools.values() if role in t.roles and t.curated]

    def search(
        self,
        text: str = "",
        stage: str | None = None,
        include_uncurated: bool = False,
        oss_only: bool = False,
        maturity: str | None = None,
        target: str | None = None,
    ) -> list[Tool]:
        needle = text.strip().lower()
        out: list[Tool] = []
        for t in self.tools.values():
            if not t.curated and not include_uncurated:
                continue
            if stage and t.stage != stage:
                continue
            if oss_only and not t.is_oss:
                continue
            if maturity:
                m = t.landscape.maturity if t.landscape else None
                if (m or "none") != maturity:
                    continue
            if target in ("docker-host", "vm") and t.kubernetes_only:
                continue
            if needle:
                hay = " ".join([t.name, t.id, t.description, " ".join(t.roles)]).lower()
                if needle not in hay:
                    continue
            out.append(t)
        out.sort(key=lambda t: (not t.curated, STAGE_IDS.index(t.stage), t.name.lower()))
        return out


def _slug(name: str) -> str:
    return "lsc-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_tool_files(directory: Path) -> list[Tool]:
    tools: list[Tool] = []
    for path in sorted(directory.glob("*.yaml")):
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for entry in entries:
            try:
                tools.append(Tool.model_validate(entry))
            except Exception as exc:  # pragma: no cover - message explicite
                raise ValueError(f"{path.name}: fiche invalide {entry.get('id')}: {exc}") from exc
    return tools


def load_landscape_index(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def default_catalog() -> Catalog:
    return build_catalog(DATA_DIR)


def build_catalog(data_dir: Path = DATA_DIR) -> Catalog:
    catalog = Catalog()
    for tool in load_tool_files(data_dir / "catalog"):
        if tool.id in catalog.tools:
            raise ValueError(f"Identifiant de fiche en double : {tool.id}")
        if tool.stage not in STAGE_IDS:
            raise ValueError(f"{tool.id}: étape inconnue {tool.stage}")
        catalog.tools[tool.id] = tool

    index = load_landscape_index(data_dir / "landscape_index.json")
    by_name = {e["name"].lower(): e for e in index}
    linked: set[str] = set()
    for tool in catalog.tools.values():
        key = (tool.landscape_name or tool.name).lower()
        entry = by_name.get(key)
        if entry:
            linked.add(entry["name"].lower())
            tool.landscape = LandscapeRef(
                category=entry.get("category"),
                subcategory=entry.get("subcategory"),
                maturity=entry.get("maturity"),
                repo_url=entry.get("repo_url"),
            )

    # Entrées du Landscape sans fiche : consultables, mais non vérifiées.
    for entry in index:
        if entry["name"].lower() in linked:
            continue
        stage = SUBCATEGORY_STAGE.get(entry.get("subcategory", ""))
        if not stage:
            continue
        tid = _slug(entry["name"])
        if tid in catalog.tools:
            continue
        catalog.tools[tid] = Tool(
            id=tid,
            name=entry["name"],
            stage=stage,
            roles=[],
            description=entry.get("description") or "",
            homepage=entry.get("homepage_url"),
            license="unknown" if entry.get("repo_url") else "proprietary",
            hosting=["docker-host", "vm", "kubernetes", "saas"],
            curated=False,
            landscape=LandscapeRef(
                category=entry.get("category"),
                subcategory=entry.get("subcategory"),
                maturity=entry.get("maturity"),
                repo_url=entry.get("repo_url"),
            ),
        )
    return catalog
