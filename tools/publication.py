# SPDX-License-Identifier: Apache-2.0
"""Préparation d'une publication (appelé par .github/workflows/publication.yml).

    python tools/publication.py verifier 0.19.0     # versions et journal cohérents
    python tools/publication.py notes 0.19.0        # notes de la publication, tirées du journal
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"\d+\.\d+\.\d+")


def section(version: str, changelog: str) -> str | None:
    """Section « ## <version> — … » du journal, sans son titre, ou None."""
    m = re.search(rf"^## {re.escape(version)}(?: —[^\n]*)?\n(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    return m.group(1).strip() if m else None


def problems(version: str, root: Path = ROOT) -> list[str]:
    found = []
    if not SEMVER.fullmatch(version):
        found.append(f"« {version} » n'est pas une version X.Y.Z")
    declared = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if declared != version:
        found.append(f"pyproject.toml annonce {declared}, pas {version}")
    init = re.search(r'__version__ = "([^"]+)"', (root / "devops_builder/__init__.py").read_text(encoding="utf-8"))
    if not init or init.group(1) != version:
        found.append(f"devops_builder/__init__.py annonce {init.group(1) if init else '?'}, pas {version}")
    if not section(version, (root / "CHANGELOG.md").read_text(encoding="utf-8")):
        found.append(f"CHANGELOG.md n'a pas de section « ## {version} — … »")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("verifier", "notes"):
        print(__doc__, file=sys.stderr)
        return 2
    action, version = argv
    if action == "verifier":
        for problem in problems(version):
            print(f"::error::{problem}")
        return 1 if problems(version) else 0
    notes = section(version, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    if notes is None:
        return 1
    print(notes)
    print("\nInstallation : `pipx install izinum-devops-builder` ou l'exécutable de votre système ci-dessous "
          "(non signé, voir le README). Provenance vérifiable : "
          "`gh attestation verify <fichier> --repo denvi44/devops-builder`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
