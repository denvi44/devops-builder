# SPDX-License-Identifier: Apache-2.0
"""Reconstruit l'index livré (devops_builder/data/landscape_index.json) depuis un landscape.yml.

Usage (mainteneurs de l'application) :
    python tools/build_landscape_index.py chemin/vers/landscape.yml

Les utilisateurs rafraîchissent plutôt leur propre index depuis l'application
(Catalogue › Rafraîchir le Landscape) ou avec `devops-builder landscape-refresh`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devops_builder.landscape import PACKAGED_INDEX, build_index, diff_indexes, load_index  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    entries = build_index(Path(sys.argv[1]).read_text(encoding="utf-8"))
    previous = load_index(PACKAGED_INDEX)
    PACKAGED_INDEX.write_text(json.dumps(entries, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(entries)} entrées écrites dans {PACKAGED_INDEX}")
    if previous:
        print(diff_indexes(previous, entries).summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
