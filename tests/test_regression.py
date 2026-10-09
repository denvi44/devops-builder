"""Non-régression : sorties figées et projets enregistrés par les versions précédentes.

Si une différence est voulue (nouveau générateur, correction), régénérer l'instantané :

    UPDATE_GOLDEN=1 pytest tests/test_regression.py

puis relire `git diff tests/golden` avant de committer : chaque ligne changée doit s'expliquer.
"""

from __future__ import annotations

import difflib
import os
import shutil
from pathlib import Path

import pytest
from snapshot import GOLDEN, corpus, packaged_catalog, render_case

from devops_builder.generators import generate
from devops_builder.model import FORMAT_VERSION, Project
from devops_builder.rules import RuleEngine

LEGACY = Path(__file__).parent / "data" / "legacy"
CASES = corpus()


def _golden(name: str) -> dict[str, str]:
    root = GOLDEN / name
    return {str(p.relative_to(root)): p.read_text(encoding="utf-8") for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("name", list(CASES), ids=list(CASES))
def test_sorties_identiques_a_l_instantane(name: str):
    current = render_case(CASES[name])
    if os.environ.get("UPDATE_GOLDEN"):
        shutil.rmtree(GOLDEN / name, ignore_errors=True)
        for rel, content in current.items():
            (GOLDEN / name / rel).parent.mkdir(parents=True, exist_ok=True)
            (GOLDEN / name / rel).write_text(content, encoding="utf-8")
        return
    expected = _golden(name)
    problems = []
    for rel in sorted(set(expected) | set(current)):
        if rel not in current:
            problems.append(f"fichier disparu : {rel}")
        elif rel not in expected:
            problems.append(f"nouveau fichier : {rel}")
        elif current[rel] != expected[rel]:
            diff = "".join(list(difflib.unified_diff(expected[rel].splitlines(True), current[rel].splitlines(True),
                                                     f"instantané/{rel}", f"actuel/{rel}", n=1))[:40])
            problems.append(f"contenu modifié : {rel}\n{diff}")
    assert not problems, "\n".join(problems)


def test_l_instantane_ne_contient_pas_de_projet_supprime():
    stale = sorted({p.name for p in GOLDEN.iterdir() if p.is_dir()} - set(CASES))
    assert stale == [], f"instantanés sans projet correspondant : {stale}"


LEGACY_FILES = sorted(LEGACY.rglob("*.devops.yaml"))


@pytest.mark.parametrize("path", LEGACY_FILES, ids=[f"{p.parent.name}/{p.stem}" for p in LEGACY_FILES])
def test_projets_des_versions_precedentes(path: Path, tmp_path: Path):
    catalog = packaged_catalog()
    project = Project.load(path)
    assert project.environments, "l'environnement du format 1 doit être migré"
    diags = RuleEngine(catalog).evaluate(project)
    assert RuleEngine.blocking(diags) == [], [d.message for d in RuleEngine.blocking(diags)]
    result = generate(project, catalog)
    assert "PIPELINE.md" in result.files and result.ir.unsupported == []
    # enregistré à nouveau : format courant, relu à l'identique
    saved = tmp_path / path.name
    project.save(saved)
    assert f"format_version: {FORMAT_VERSION}" in saved.read_text(encoding="utf-8")
    assert Project.load(saved).model_dump() == project.model_dump()


def test_projet_format_1_equivalent_a_l_exemple_actuel():
    """L'exemple de la 0.1 et celui d'aujourd'hui décrivent le même pipeline : mêmes briques."""
    old = Project.load(LEGACY / "0.1.0" / "01-web-hote-docker.devops.yaml")
    new = Project.load(Path(__file__).parents[1] / "devops_builder" / "data" / "examples" / "01-web-hote-docker.devops.yaml")
    assert old.tool_ids() == new.tool_ids()
    assert [e.kind for e in old.environments] == ["production"]
