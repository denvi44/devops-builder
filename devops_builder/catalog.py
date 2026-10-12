# SPDX-License-Identifier: Apache-2.0
"""Chargement du catalogue : fiches livrées, catalogue personnel, index du CNCF Landscape.

Ordre de fusion : fiches livrées, puis fiches personnelles (dossier utilisateur), puis
corrections des fiches livrées (corrections.yaml), puis entrées du Landscape sans fiche.
Une fiche personnelle ou une correction invalide est écartée et signalée dans
`catalog.errors`, sans empêcher l'application de démarrer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .model import STAGE_IDS, LandscapeRef, Tool

DATA_DIR = Path(__file__).parent / "data"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
# Champs qu'une correction peut changer sur une fiche livrée
CORRECTABLE = ("lifecycle", "lifecycle_note", "license", "repo", "replacements", "verified", "homepage", "description")

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
    "Database": "data",
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

# Sous-catégories dont les outils servent légitimement à plusieurs étapes.
SUBCATEGORY_EXTRA_STAGES = {
    "Automation & Configuration": ["deploy"],
    "Security & Compliance": ["test", "platform"],
    "Key Management": ["security"],
    "Database": ["platform"],  # rangées en Plateforme avant la 0.8 : les projets existants restent valides
    "Application Definition & Image Build": ["deploy"],
    "Continuous Integration & Delivery": ["test", "deploy"],
}


@dataclass
class Catalog:
    tools: dict[str, Tool] = field(default_factory=dict)
    # entrée du Landscape (lsc-…) devenue une fiche : l'ancien identifiant mène à la fiche
    aliases: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    user_dir: Path | None = None
    index_path: Path | None = None

    # ----------------------------------------------------------------- access
    def resolve(self, tool_id: str) -> str:
        return self.aliases.get(tool_id, tool_id)

    def get(self, tool_id: str) -> Tool | None:
        return self.tools.get(self.aliases.get(tool_id, tool_id))

    def __getitem__(self, tool_id: str) -> Tool:
        return self.tools[self.aliases.get(tool_id, tool_id)]

    def __contains__(self, tool_id: str) -> bool:
        return self.aliases.get(tool_id, tool_id) in self.tools

    def user_tools(self) -> list[Tool]:
        return [t for t in self.tools.values() if t.origin == "utilisateur"]

    def landscape_entry_for(self, tool: Tool) -> dict | None:
        """Entrée brute du Landscape d'une fiche (ou d'une entrée non vérifiée)."""
        from .landscape import load_index
        key = (tool.landscape_name or tool.name).lower()
        return next((e for e in load_index(self.index_path) if e["name"].lower() == key), None)

    def curated(self) -> list[Tool]:
        return [t for t in self.tools.values() if t.curated]

    def can_place(self, tool_id: str, stage: str) -> bool:
        tool = self.tools.get(tool_id)
        return tool is not None and tool.can_go_in(stage)

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


def _attach_param_schemas(catalog: Catalog, path: Path) -> None:
    """Rattache data/params.yaml aux fiches ; contrôle le schéma au chargement."""
    import re

    from .model import ParamSpec
    from .params import check_value

    if not path.exists():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for tool_id, specs in data.items():
        if tool_id.startswith("_"):
            continue  # ancres YAML partagées
        tool = catalog.tools.get(tool_id)
        if tool is None:
            raise ValueError(f"params.yaml : fiche inconnue {tool_id}")
        if tool.params:
            raise ValueError(f"{tool_id} : paramètres à la fois en ligne et dans params.yaml")
        schema = {k: ParamSpec.model_validate(v) for k, v in specs.items()}
        for key, spec in schema.items():
            if spec.pattern:
                re.compile(spec.pattern)
            if spec.default is not None and "{app}" not in str(spec.default) and check_value(spec, spec.default):
                raise ValueError(f"{tool_id}.{key} : la valeur par défaut ne respecte pas le schéma")
        tool.param_schema = schema


@lru_cache(maxsize=1)
def default_catalog() -> Catalog:
    """Catalogue de l'application : fiches livrées + catalogue personnel + index courant."""
    from . import userdata
    from .landscape import current_index_path
    return build_catalog(DATA_DIR, user_dir=userdata.catalog_dir(), index_path=current_index_path())


def reload_default_catalog() -> Catalog:
    default_catalog.cache_clear()
    return default_catalog()


def check_fiche(tool: Tool, existing: dict[str, Tool] | None = None) -> list[str]:
    """Contrôles d'une fiche au-delà du schéma : identifiant, étapes, doublon."""
    problems = []
    if not ID_PATTERN.match(tool.id) or tool.id.startswith("lsc-"):
        problems.append(f"identifiant « {tool.id} » invalide (minuscules, chiffres, tirets ; pas de préfixe lsc-)")
    for s in (tool.stage, *tool.extra_stages):
        if s not in STAGE_IDS:
            problems.append(f"étape inconnue « {s} »")
    if existing is not None and tool.id in existing:
        problems.append(f"l'identifiant « {tool.id} » est déjà pris par « {existing[tool.id].name} »")
    return problems


def load_user_fiches(directory: Path, existing: dict[str, Tool]) -> tuple[list[Tool], list[str]]:
    tools: list[Tool] = []
    errors: list[str] = []
    if not directory.is_dir():
        return tools, errors
    taken = dict(existing)
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except yaml.YAMLError as exc:
            errors.append(f"{path.name} : YAML illisible ({exc})")
            continue
        for entry in data if isinstance(data, list) else [data]:
            if not isinstance(entry, dict):
                errors.append(f"{path.name} : une fiche doit être un dictionnaire YAML")
                continue
            entry = {k: v for k, v in entry.items() if k not in ("origin", "corrections", "curated", "landscape")}
            try:
                tool = Tool.model_validate(entry)
            except Exception as exc:
                errors.append(f"{path.name} : fiche {entry.get('id', '?')} invalide — {_short(exc)}")
                continue
            problems = check_fiche(tool, taken)
            if problems:
                errors.append(f"{path.name} : " + " ; ".join(problems))
                continue
            tool.origin = "utilisateur"
            taken[tool.id] = tool
            tools.append(tool)
    return tools, errors


def _short(exc: Exception) -> str:
    text = str(exc).splitlines()
    return " ".join(line.strip() for line in text[:4])


def apply_corrections(catalog: Catalog, path: Path) -> None:
    if not path.exists():
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        catalog.errors.append(f"{path.name} : YAML illisible ({exc})")
        return
    if not isinstance(data, dict):
        catalog.errors.append(f"{path.name} : un dictionnaire identifiant → champs est attendu")
        return
    for tool_id, patch in data.items():
        tool = catalog.tools.get(tool_id)
        if tool is None:
            catalog.errors.append(f"{path.name} : la fiche « {tool_id} » n'existe pas (ou plus)")
            continue
        if not isinstance(patch, dict):
            catalog.errors.append(f"{path.name} : {tool_id} — champs attendus sous forme de dictionnaire")
            continue
        unknown = sorted(set(patch) - set(CORRECTABLE))
        if unknown:
            catalog.errors.append(f"{path.name} : {tool_id} — champ(s) non corrigeable(s) : {', '.join(unknown)}")
            continue
        current = tool.model_dump()
        try:
            fixed = Tool.model_validate({**current, **patch})
        except Exception as exc:
            catalog.errors.append(f"{path.name} : {tool_id} — correction invalide : {_short(exc)}")
            continue
        fixed.corrections = {k: current.get(k) for k in patch if current.get(k) != patch[k]}
        fixed.param_schema = tool.param_schema
        catalog.tools[tool_id] = fixed


def build_catalog(data_dir: Path = DATA_DIR, user_dir: Path | None = None,
                  index_path: Path | None = None) -> Catalog:
    catalog = Catalog(user_dir=user_dir, index_path=index_path or data_dir / "landscape_index.json")
    for tool in load_tool_files(data_dir / "catalog"):
        if tool.id in catalog.tools:
            raise ValueError(f"Identifiant de fiche en double : {tool.id}")
        for s in (tool.stage, *tool.extra_stages):
            if s not in STAGE_IDS:
                raise ValueError(f"{tool.id}: étape inconnue {s}")
        catalog.tools[tool.id] = tool

    _attach_param_schemas(catalog, data_dir / "params.yaml")

    if user_dir is not None:
        user_tools, errors = load_user_fiches(user_dir / "fiches", catalog.tools)
        catalog.errors.extend(errors)
        for tool in user_tools:
            catalog.tools[tool.id] = tool

    index = load_landscape_index(catalog.index_path)
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
            slug = _slug(entry["name"])
            if slug != tool.id:
                catalog.aliases[slug] = tool.id

    if user_dir is not None:
        apply_corrections(catalog, user_dir / "corrections.yaml")

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
            extra_stages=SUBCATEGORY_EXTRA_STAGES.get(entry.get("subcategory", ""), []),
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
