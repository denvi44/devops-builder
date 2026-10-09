"""Écriture du catalogue personnel : fiches créées depuis le Landscape, corrections de fiches.

Les fichiers livrés avec l'application ne sont jamais modifiés : tout va dans le dossier
utilisateur (voir userdata), relu à chaque chargement du catalogue.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from . import userdata
from .catalog import CORRECTABLE, SUBCATEGORY_EXTRA_STAGES, SUBCATEGORY_STAGE, Catalog, check_fiche
from .model import Tool

# Sous-catégories dont les projets ne tournent que sur Kubernetes
K8S_SUBCATEGORIES = {"Service Mesh", "Scheduling & Orchestration", "Cloud Native Network",
                     "Certified Kubernetes - Distribution", "Certified Kubernetes - Hosted",
                     "Certified Kubernetes - Installer", "Chaos Engineering"}
# Champs écrits dans un fichier de fiche, dans cet ordre
FICHE_FIELDS = ("id", "name", "kind", "stage", "extra_stages", "roles", "description", "homepage", "license", "repo",
                "hosting", "provides", "requires", "forges", "provider", "lifecycle", "lifecycle_note",
                "replacements", "alternatives", "dev_only", "landscape_name", "verified")


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not s or not s[0].isalpha():
        s = "outil-" + s
    return s[:40].rstrip("-")


def unique_id(base: str, catalog: Catalog) -> str:
    candidate, n = base, 2
    while candidate in catalog.tools:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def draft_from_landscape(entry: dict, catalog: Catalog, today: date | None = None) -> dict[str, Any]:
    """Fiche pré-remplie depuis une entrée du Landscape ; à relire avant enregistrement.

    La licence reste « unknown » : le Landscape ne la donne pas. license_from_repo() la lit
    sur la forge quand le réseau le permet.
    """
    sub = entry.get("subcategory") or ""
    k8s = sub in K8S_SUBCATEGORIES
    day = (today or date.today()).isoformat()
    archived = {"lifecycle": "archived", "lifecycle_note": f"Projet archivé selon le CNCF Landscape ({day})."} \
        if entry.get("maturity") == "archived" else {}
    return {
        "id": unique_id(slug(entry["name"]), catalog),
        "name": entry["name"],
        "stage": SUBCATEGORY_STAGE.get(sub, "platform"),
        "extra_stages": list(SUBCATEGORY_EXTRA_STAGES.get(sub, [])),
        "roles": [],
        "description": entry.get("description") or "",
        "homepage": entry.get("homepage_url"),
        "license": "unknown",  # à vérifier : le Landscape ne donne pas la licence
        "repo": entry.get("repo_url"),
        "hosting": ["kubernetes"] if k8s else ["docker-host", "vm", "kubernetes"],
        "landscape_name": entry["name"],
        "verified": day,
        **archived,
    }


def license_from_repo(url: str | None) -> str | None:
    """Licence SPDX lue sur GitHub ou GitLab.com ; None si inconnue ou injoignable."""
    if not url:
        return None
    from .health import fetch_repo, github_token, normalize_license
    st = fetch_repo(url, github_token())
    return normalize_license(st.license) if st.usable and st.found else None


def fiche_yaml(data: dict[str, Any]) -> str:
    ordered = {k: data[k] for k in FICHE_FIELDS if k in data and data[k] not in (None, [], "")}
    ordered.update({k: v for k, v in data.items() if k not in ordered and k not in FICHE_FIELDS and v not in (None, [])})
    head = "# Fiche personnelle DevOps Builder : relue au chargement, avec les mêmes contrôles que les fiches livrées.\n"
    return head + yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, width=120)


def validate_fiche(data: dict[str, Any], catalog: Catalog, editing: str | None = None) -> tuple[Tool | None, list[str]]:
    """Contrôle une fiche saisie ; `editing` = identifiant de la fiche personnelle modifiée."""
    try:
        tool = Tool.model_validate({k: v for k, v in data.items() if v is not None})
    except Exception as exc:
        lines = [line.strip() for line in str(exc).splitlines()[1:6] if line.strip()]
        return None, lines or [str(exc)]
    existing = {k: v for k, v in catalog.tools.items() if k != editing}
    problems = check_fiche(tool, existing)
    for ref in (*tool.replacements, *tool.alternatives):
        if ref not in catalog:
            problems.append(f"fiche « {ref} » inexistante (remplaçants ou alternatives)")
    return (tool if not problems else None), problems


def fiche_path(tool_id: str, directory: Path | None = None) -> Path:
    return (directory or userdata.user_fiches_dir()) / f"{tool_id}.yaml"


def save_fiche(data: dict[str, Any], catalog: Catalog, editing: str | None = None,
               directory: Path | None = None) -> Path:
    tool, problems = validate_fiche(data, catalog, editing)
    if problems:
        raise ValueError("; ".join(problems))
    assert tool is not None
    directory = directory or userdata.user_fiches_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if editing and editing != tool.id:
        fiche_path(editing, directory).unlink(missing_ok=True)
    path = fiche_path(tool.id, directory)
    path.write_text(fiche_yaml(data), encoding="utf-8")
    return path


def delete_fiche(tool_id: str, directory: Path | None = None) -> bool:
    path = fiche_path(tool_id, directory)
    if path.exists():
        path.unlink()
        return True
    return False


def tool_to_data(tool: Tool) -> dict[str, Any]:
    """Champs d'une fiche tels qu'on les écrirait à la main (valeurs par défaut omises)."""
    data = tool.model_dump(exclude_defaults=True, exclude={"landscape", "curated", "origin", "corrections"})
    data.update(id=tool.id, name=tool.name, stage=tool.stage)
    return data


# ----------------------------------------------------------------- corrections
def read_corrections(path: Path | None = None) -> dict[str, dict]:
    path = path or userdata.corrections_file()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def write_corrections(patches: dict[str, dict], path: Path | None = None) -> Path:
    """Fusionne des corrections (identifiant → champs) dans corrections.yaml."""
    path = path or userdata.corrections_file()
    current = read_corrections(path)
    for tool_id, patch in patches.items():
        bad = set(patch) - set(CORRECTABLE)
        if bad:
            raise ValueError(f"{tool_id} : champ(s) non corrigeable(s) {sorted(bad)}")
        current.setdefault(tool_id, {}).update(patch)
    path.parent.mkdir(parents=True, exist_ok=True)
    _dump_corrections(current, path)
    return path


def _dump_corrections(current: dict, path: Path) -> None:
    head = ("# Corrections des fiches livrées par DevOps Builder (identifiant → champs remplacés).\n"
            f"# Champs corrigeables : {', '.join(CORRECTABLE)}.\n")
    path.write_text(head + yaml.safe_dump(current, sort_keys=True, allow_unicode=True, width=120), encoding="utf-8")


def remove_correction(tool_id: str, path: Path | None = None) -> bool:
    path = path or userdata.corrections_file()
    current = read_corrections(path)
    if tool_id not in current:
        return False
    del current[tool_id]
    if current:
        _dump_corrections(current, path)
    else:
        path.unlink(missing_ok=True)
    return True


def apply_fixes(fixes: list[tuple[str, dict]], catalog: Catalog) -> list[str]:
    """Applique des corrections proposées par l'entretien : fichier de la fiche personnelle,
    ou corrections.yaml pour une fiche livrée. Renvoie les identifiants modifiés."""
    packaged: dict[str, dict] = {}
    changed: list[str] = []
    for tool_id, patch in fixes:
        tool = catalog.get(tool_id)
        if tool is None:
            continue
        if tool.origin == "utilisateur":
            data = tool_to_data(tool)
            data.update(patch)
            save_fiche(data, catalog, editing=tool.id)
        else:
            packaged.setdefault(tool.id, {}).update(patch)
        changed.append(tool.id)
    if packaged:
        write_corrections(packaged)
    return changed
