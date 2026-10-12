# SPDX-License-Identifier: Apache-2.0
"""Index du CNCF Landscape : construction depuis landscape.yml, rafraîchissement, écarts.

L'index livré avec l'application (data/landscape_index.json) date de la version. Le
rafraîchissement télécharge le landscape.yml courant et écrit un index dans le dossier
de l'utilisateur, qui prend alors le pas sur celui livré.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import userdata

LANDSCAPE_URL = "https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml"
PACKAGED_INDEX = Path(__file__).parent / "data" / "landscape_index.json"
EXCLUDED_CATEGORIES = {
    "CNCF Members", "Special", "Wasm", "AI Agent", "Inference", "Data",
    "Training", "AI Native Infra",
}
EXCLUDED_SUBCATEGORIES = {"Certified Kubernetes - AI Platform"}


def build_index(landscape: str | dict) -> list[dict]:
    """landscape.yml → entrées utiles à la palette (catégories écartées, doublons retirés)."""
    data = yaml.safe_load(landscape) if isinstance(landscape, str) else landscape
    if not isinstance(data, dict) or "landscape" not in data:
        raise ValueError("Ce fichier n'est pas un landscape.yml du CNCF (clé « landscape » absente).")
    seen_repos: set[str] = set()
    seen_names: set[str] = set()
    entries: list[dict] = []
    for category in data["landscape"]:
        if category["name"] in EXCLUDED_CATEGORIES:
            continue
        for sub in category.get("subcategories") or []:
            if sub["name"] in EXCLUDED_SUBCATEGORIES:
                continue
            for item in sub.get("items") or []:
                name = item["name"].strip()
                repo = (item.get("repo_url") or "").rstrip("/").lower()
                if repo and repo in seen_repos:
                    continue
                if name.lower() in seen_names:
                    continue
                if repo:
                    seen_repos.add(repo)
                seen_names.add(name.lower())
                description = (item.get("description") or "").strip().replace("\n", " ")
                entries.append({
                    "name": name,
                    "category": category["name"],
                    "subcategory": sub["name"],
                    "maturity": item.get("project"),
                    "repo_url": item.get("repo_url"),
                    "homepage_url": item.get("homepage_url"),
                    "description": description[:240],
                })
    return entries


def current_index_path() -> Path:
    user = userdata.landscape_index()
    return user if user.exists() else PACKAGED_INDEX


def load_index(path: Path | None = None) -> list[dict]:
    path = path or current_index_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class IndexDiff:
    total: int
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    newly_archived: list[str] = field(default_factory=list)
    maturity_changes: list[tuple[str, str | None, str | None]] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{self.total} entrées", f"{len(self.added)} ajoutée(s)", f"{len(self.removed)} retirée(s)"]
        if self.newly_archived:
            parts.append(f"{len(self.newly_archived)} nouvellement archivée(s) : {', '.join(self.newly_archived)}")
        return ", ".join(parts)


def diff_indexes(old: list[dict], new: list[dict]) -> IndexDiff:
    before = {e["name"]: e for e in old}
    after = {e["name"]: e for e in new}
    out = IndexDiff(total=len(new), added=sorted(set(after) - set(before)), removed=sorted(set(before) - set(after)))
    for name in sorted(set(after) & set(before)):
        a, b = before[name].get("maturity"), after[name].get("maturity")
        if a != b:
            out.maturity_changes.append((name, a, b))
            if b == "archived":
                out.newly_archived.append(name)
    return out


def download(url: str = LANDSCAPE_URL, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "devops-builder"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL https fixée ou choisie)
        return resp.read().decode("utf-8")


def refresh(source: str | Path | None = None, dest: Path | None = None) -> tuple[IndexDiff, Path]:
    """Télécharge (ou lit) landscape.yml, écrit l'index utilisateur et renvoie les écarts."""
    if source is None or str(source).startswith(("http://", "https://")):
        text = download(str(source or LANDSCAPE_URL))
    else:
        text = Path(source).read_text(encoding="utf-8")
    entries = build_index(text)
    if len(entries) < 100:
        raise ValueError(f"Index anormalement court ({len(entries)} entrées) : rafraîchissement abandonné.")
    previous = load_index()
    dest = dest or userdata.landscape_index()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(entries, ensure_ascii=False, indent=0), encoding="utf-8")
    return diff_indexes(previous, entries), dest


def reset() -> bool:
    """Revient à l'index livré avec l'application."""
    path = userdata.landscape_index()
    if path.exists():
        path.unlink()
        return True
    return False
