# SPDX-License-Identifier: Apache-2.0
"""Licence Apache 2.0 : texte officiel, métadonnées, en-têtes, inventaire des licences tierces."""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
# Empreinte du texte publié sur https://www.apache.org/licenses/LICENSE-2.0.txt
APACHE_2_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
HEADER = "# SPDX-License-Identifier: Apache-2.0"


def test_texte_officiel_de_la_licence():
    assert hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest() == APACHE_2_SHA256


def test_metadonnees_du_paquet():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE", "NOTICE"]
    assert project["urls"]["Source"] == "https://github.com/denvi44/devops-builder"


def test_chaque_fichier_python_porte_l_en_tete_spdx():
    missing = []
    for path in sorted(ROOT.glob("**/*.py")):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in (".git", "build", "dist") or "__pycache__" in rel.parts or rel.parts[:2] == ("tests", "golden"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()[:2]
        if HEADER not in lines:
            missing.append(str(rel))
    assert not missing, f"en-tête « {HEADER} » absent : {missing}"


def test_chaque_dependance_est_inventoriee():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    doc = (ROOT / "docs" / "licences-tierces.md").read_text(encoding="utf-8").lower()
    names = [re.split(r"[<>=!~\[ ;]", d, maxsplit=1)[0] for d in project["dependencies"]]
    names += [re.split(r"[<>=!~\[ ;]", d, maxsplit=1)[0] for d in project["optional-dependencies"]["dev"]]
    absent = [n for n in names if n.lower() not in doc]
    assert not absent, f"dépendances absentes de docs/licences-tierces.md : {absent}"


def test_notice_attribue_les_donnees_du_landscape():
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "landscape_index.json" in notice and "Apache" in notice
    assert (ROOT / "devops_builder" / "data" / "landscape_index.json").exists()
