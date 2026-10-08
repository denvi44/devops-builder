"""Construit data/landscape_index.json à partir du landscape.yml du CNCF.

Usage :
    python tools/build_landscape_index.py chemin/vers/landscape.yml

- retire les catégories écartées par le plan (membres, partenaires, Wasm, IA…) ;
- dédoublonne par repo_url (les chemins secondaires recréent des entrées) ;
- ne garde que les champs utiles à la palette.

Le script signale aussi les écarts avec l'index précédent (ajouts, retraits,
projets passés en « archived ») pour l'entretien des fiches.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

EXCLUDED_CATEGORIES = {
    "CNCF Members", "Special", "Wasm", "AI Agent", "Inference", "Data",
    "Training", "AI Native Infra",
}
EXCLUDED_SUBCATEGORIES = {"Certified Kubernetes - AI Platform"}
OUT = Path(__file__).resolve().parents[1] / "devops_builder" / "data" / "landscape_index.json"


def build(landscape_path: Path) -> list[dict]:
    data = yaml.safe_load(landscape_path.read_text(encoding="utf-8"))
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


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    entries = build(Path(sys.argv[1]))
    previous = {}
    if OUT.exists():
        previous = {e["name"]: e for e in json.loads(OUT.read_text(encoding="utf-8"))}
    current = {e["name"]: e for e in entries}
    added = sorted(set(current) - set(previous))
    removed = sorted(set(previous) - set(current))
    archived = sorted(
        n for n in current
        if current[n].get("maturity") == "archived"
        and previous.get(n, {}).get("maturity") not in (None, "archived")
    )
    OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(entries)} entrées écrites dans {OUT}")
    if previous:
        print(f"Ajoutées : {len(added)}  Retirées : {len(removed)}  Nouvellement archivées : {archived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
