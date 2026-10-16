# SPDX-License-Identifier: Apache-2.0
"""Lot 0.16 : contrat de compatibilité des fichiers projet (voir docs/format.md)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from devops_builder.model import FORMAT_VERSION, Project, ProjectFormatError

ROOT = Path(__file__).parent.parent
LEGACY = Path(__file__).parent / "data" / "legacy"
LEGACY_FILES = sorted(LEGACY.rglob("*.devops.yaml"))
# Seules différences admises à l'enregistrement d'un ancien fichier : les migrations de docs/format.md
MIGRATED = {"format_version", "environment"}


def _flat(d, pre: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flat(v, f"{pre}.{k}" if pre else str(k)))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flat(v, f"{pre}[{i}]"))
    else:
        out[pre] = d
    return out


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split("."))


@pytest.mark.parametrize("path", LEGACY_FILES, ids=[f"{p.parent.name}/{p.stem}" for p in LEGACY_FILES])
def test_aucune_valeur_perdue_a_l_enregistrement(path: Path):
    before = _flat(yaml.safe_load(path.read_text(encoding="utf-8")))
    after = _flat(yaml.safe_load(Project.load(path).to_yaml()))
    lost = {k: v for k, v in before.items() if k not in after and k not in MIGRATED and v not in (None, "", [], {})}
    changed = {k: (v, after[k]) for k, v in before.items() if k in after and after[k] != v and k not in MIGRATED}
    assert not lost and not changed, f"perdu : {lost} ; modifié : {changed}"


def test_chaque_version_publiee_a_ses_fichiers():
    """À chaque version, les fichiers écrits par la précédente rejoignent le corpus."""
    current = _version(re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1))
    have = {_version(p.name) for p in LEGACY.iterdir() if p.is_dir() and any(p.glob("*.devops.yaml"))}
    expected = {(0, minor, 0) for minor in range(1, 16)}
    if current[:2] > (0, 16):
        expected.add((current[0], current[1] - 1, 0) if current[1] else current)
    assert expected <= have, f"versions sans fichier dans tests/data/legacy : {sorted(expected - have)}"


def test_format_plus_recent_refuse_avec_un_message_clair():
    with pytest.raises(ProjectFormatError, match=f"format {FORMAT_VERSION + 1} .* mettre à jour"):
        Project.from_yaml(f"format_version: {FORMAT_VERSION + 1}\nname: Futur\n")


def test_champs_inconnus_conserves_et_signales():
    text = ("format_version: 2\nname: Boutique\nrevue: equipe-a\napp:\n  image_name: shop\n  sante: /healthz\n"
            "stages:\n  build:\n  - uid: abcd1234\n    tool: buildkit\n    commentaire: garder\n")
    p = Project.from_yaml(text)
    assert p.unknown_fields() == ["revue", "app.sante", "stages.build.buildkit.commentaire"]
    again = yaml.safe_load(p.to_yaml())
    assert again["revue"] == "equipe-a" and again["app"]["sante"] == "/healthz"
    assert again["stages"]["build"][0]["commentaire"] == "garder"
    assert Project.from_yaml(p.to_yaml()).unknown_fields() == p.unknown_fields()
    assert Project.load(LEGACY_FILES[-1]).unknown_fields() == []


@pytest.mark.parametrize("text, message", [
    ("name: [", "YAML invalide ligne 1, colonne 8 : le fichier s'arrête au milieu d'une valeur"),
    ("- a\n- b\n", "ne décrit pas un projet"),
    ("name: x\ntarget: 3\n", "target : texte attendu"),
    ("cloud_auth: magie\n", "« magie » refusée, attendu : 'oidc' ou 'static'"),
    ("environments:\n- id: p\n  kindd: x\n", "environments.0.kindd : champ inconnu"),
])
def test_erreurs_lisibles(text: str, message: str):
    with pytest.raises(ProjectFormatError) as exc:
        Project.from_yaml(text)
    assert message in str(exc.value)


def test_documentation_du_format_a_jour():
    doc = (ROOT / "docs" / "format.md").read_text(encoding="utf-8")
    assert f"Format courant : **{FORMAT_VERSION}**" in doc
    for field in Project.model_fields:
        assert f"`{field}`" in doc, f"champ {field} absent de docs/format.md"
