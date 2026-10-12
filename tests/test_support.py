# SPDX-License-Identifier: Apache-2.0
"""Lot 0.16 : niveau de prise en charge des fiches, confronté à ce que les générateurs produisent vraiment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest
from test_data import CATALOG, COMPOSE, ENGINE, K3S_HELM, project

from devops_builder.generators import render
from devops_builder.model import SUPPORT, Tool
from devops_builder.support import matrix_markdown

GH = ("github", "github-actions", "buildkit")
BASES = [
    ("kubernetes", K3S_HELM),
    ("docker-host", COMPOSE),
    ("vm", GH + ("ghcr", "ansible")),
    ("kubernetes-managed", GH + ("aws", "eks", "ecr", "helm", "opentofu")),
    ("kubernetes-managed", GH + ("gcp", "gke", "helm", "opentofu")),
    ("kubernetes-managed", GH + ("azure", "aks", "helm", "opentofu")),
    ("kubernetes-managed", GH + ("outscale", "helm", "opentofu")),
]
# Contexte naturel des fiches sans générateur : elles restent sans fichier même là où elles ont leur place.
NATURAL = {
    "oks": ("kubernetes-managed", GH + ("outscale", "oks", "helm", "opentofu")),
    "app-mesh": ("kubernetes-managed", GH + ("aws", "eks", "ecr", "helm", "opentofu")),
    "cloudformation": ("kubernetes-managed", GH + ("aws", "eks", "ecr", "helm")),
    "bicep": ("kubernetes-managed", GH + ("azure", "aks", "helm")),
    "thanos": ("kubernetes", K3S_HELM + ("prometheus",)),
    "packer": ("vm", GH + ("ghcr", "ansible", "aws", "opentofu")),
}


def _covered_in(target: str, tools: tuple[str, ...], extra: str) -> bool:
    try:
        p = project(target, *tools, extra)
    except (KeyError, ValueError):
        return False
    return extra in render(p, CATALOG)[1].covered


@lru_cache(maxsize=1)
def coverage() -> frozenset[str]:
    from snapshot import corpus

    covered: set[str] = set()
    for p in corpus().values():
        covered |= render(p, CATALOG)[1].covered
    for t in CATALOG.curated():
        if t.id in covered:
            continue
        bases = BASES + ([NATURAL[t.id]] if t.id in NATURAL else [])
        if any(_covered_in(target, tools, t.id) for target, tools in bases):
            covered.add(t.id)
    return frozenset(covered)


def test_chaque_fiche_a_un_niveau_et_une_raison():
    for t in CATALOG.curated():
        assert t.support in SUPPORT
        if t.support == "experimental":
            assert t.support_note.strip(), f"{t.id} : une fiche expérimentale dit pourquoi (support_note)"


def test_niveau_conforme_aux_generateurs():
    covered = coverage()
    wrong_manual = sorted(t.id for t in CATALOG.curated() if t.support == "manual" and t.id in covered)
    missing = sorted(t.id for t in CATALOG.curated() if t.support != "manual" and t.id not in covered)
    assert not wrong_manual, f"générées mais marquées « manual » : {wrong_manual}"
    assert not missing, f"jamais générées (ajouter un projet au corpus ou marquer « manual ») : {missing}"


def test_niveau_effectif_des_fiches_hors_catalogue():
    uncurated = next(t for t in CATALOG.tools.values() if not t.curated)
    assert uncurated.support_level == "manual"
    mine = Tool(id="mon-outil", name="Mon outil", stage="build", origin="utilisateur")
    assert mine.support_level == "manual"


def test_regle_r50_rappelle_la_limite():
    p = project("kubernetes", "gitea", "woodpecker", "buildkit", "k3s", "helm")
    found = [d for d in ENGINE.evaluate(p) if d.rule_id == "R50"]
    assert len(found) == 1 and "porte d'approbation" in found[0].message
    assert not [d for d in ENGINE.evaluate(project("kubernetes", *K3S_HELM)) if d.rule_id == "R50"]


def test_matrice_publiee_a_jour():
    doc = Path(__file__).parent.parent / "docs" / "prise-en-charge.md"
    assert doc.read_text(encoding="utf-8") == matrix_markdown(CATALOG), \
        "docs/prise-en-charge.md périmé : python -m devops_builder.support > docs/prise-en-charge.md"


@pytest.mark.parametrize("level", ["experimental", "manual"])
def test_palette_annonce_le_niveau(level):
    from devops_builder.ui.palette import PaletteWidget

    tool = next(t for t in CATALOG.curated() if t.support == level)
    assert PaletteWidget._label(tool).endswith(("β", "⚙"))
    assert SUPPORT[level].lower() in PaletteWidget._tooltip(tool)
