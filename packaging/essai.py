# SPDX-License-Identifier: Apache-2.0
"""Essai d'un exécutable construit par PyInstaller, sur le système qui l'a construit.

    python packaging/essai.py CHEMIN_DE_L_EXECUTABLE VERSION_ATTENDUE

Version, vérification et génération d'un projet (catalogue et modèles embarqués), puis
démarrage de l'interface sans écran : elle doit encore tourner au bout de quelques secondes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "tests/data/legacy/0.17.0/identite-dex-compose-github.devops.yaml"
ENV = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "DEVOPS_BUILDER_HOME": tempfile.mkdtemp(prefix="essai-")}


def run(exe: str, *args: str) -> str:
    r = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=300)
    out = r.stdout + r.stderr
    if r.returncode:
        sys.exit(f"échec ({r.returncode}) : {' '.join(args)}\n{out}")
    return out


def main() -> None:
    exe, version = sys.argv[1], sys.argv[2]
    out = run(exe, "--version")
    assert out.split() == ["devops-builder", version], out
    run(exe, "check", str(PROJECT))
    with tempfile.TemporaryDirectory() as tmp:
        run(exe, "generate", str(PROJECT), "-o", tmp)
        files = [p for p in Path(tmp).rglob("*") if p.is_file()]
        assert len(files) > 10, files
        print(f"generate : {len(files)} fichiers")
    gui = subprocess.Popen([exe], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(20)
    if gui.poll() is not None:
        sys.exit(f"l'interface s'est arrêtée ({gui.returncode}) :\n{gui.stdout.read().decode(errors='replace')}")
    gui.kill()
    gui.wait()
    print(f"devops-builder {version} : version, check, generate et interface en ordre")


if __name__ == "__main__":
    main()
