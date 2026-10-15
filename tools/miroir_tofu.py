# SPDX-License-Identifier: Apache-2.0
"""Miroir local des providers OpenTofu utilisés par les fichiers de référence.

    python tools/miroir_tofu.py DOSSIER [--platform linux_amd64]

Rassemble les couples (source, contrainte) des versions.tf de tests/golden dans un module
provisoire, puis lance « tofu providers mirror ». Le dossier obtenu se donne aux tests par
DEVOPS_BUILDER_TOFU_MIRROR : « tofu validate » tourne alors sur toutes les piles sans réseau.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIR = re.compile(r'source\s*=\s*"([^"]+)"\s*\n\s*version\s*=\s*"([^"]+)"')


def providers() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for tf in sorted(ROOT.glob("tests/golden/*/infra/*/versions.tf")):
        for source, constraint in PAIR.findall(tf.read_text()):
            found.setdefault(source, set()).add(constraint)
    return found


def module(found: dict[str, set[str]]) -> str:
    lines = ["terraform {", "  required_providers {"]
    for source, constraints in sorted(found.items()):
        name = source.split("/")[-1]
        lines.append(f'    {name} = {{ source = "{source}", version = "{", ".join(sorted(constraints))}" }}')
    return "\n".join([*lines, "  }", "}", ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dossier", type=Path)
    parser.add_argument("--platform", default="linux_amd64")
    args = parser.parse_args()
    found = providers()
    if not found:
        print("aucun provider trouvé dans tests/golden", file=sys.stderr)
        return 1
    args.dossier.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "main.tf").write_text(module(found))
        print(module(found))
        return subprocess.run(["tofu", "providers", "mirror", f"-platform={args.platform}",
                               str(args.dossier.resolve())], cwd=tmp).returncode


if __name__ == "__main__":
    raise SystemExit(main())
