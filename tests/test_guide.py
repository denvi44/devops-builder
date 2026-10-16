# SPDX-License-Identifier: Apache-2.0
"""Le guide suit l'application : chaque fichier cité par un tutoriel est généré pour son projet."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.rules import RuleEngine
from devops_builder.starter import build_starter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from tutoriels import TUTORIALS  # noqa: E402

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
GUIDE = ROOT / "docs" / "guide" / "tutoriels"
# créés par les gestes du mode d'emploi, pas par la génération
CREATED_LATER = {"deploy/secrets/", "infra/terraform/terraform.tfvars", "plan.tfplan"}
PATH = re.compile(r"`((?:\.?[\w.-]+/)+[\w.*-]*|\.?[\w.-]+\.(?:yml|yaml|md|json|sh|tf|example))`")


def cited(text: str) -> set[str]:
    return {m for m in PATH.findall(text)
            if not m.startswith(("/", "~")) and "*" not in m and not m.endswith(".devops.yaml")} - CREATED_LATER


@pytest.mark.parametrize("slug", sorted(TUTORIALS))
def test_fichiers_cites_generes(slug):
    page = (GUIDE / f"{slug}.md").read_text(encoding="utf-8")
    project = build_starter(TUTORIALS[slug], CATALOG)
    files = set(generate(project, CATALOG, ENGINE, allow_blocking=True).files)
    names = {Path(f).name for f in files}
    missing = []
    for ref in sorted(cited(page)):
        if ref.endswith("/"):
            ok = any(f.startswith(ref) for f in files)
        elif "/" in ref:
            ok = ref in files
        else:
            ok = ref in names
        if not ok:
            missing.append(ref)
    assert not missing, f"{slug}.md cite des fichiers absents de la génération : {missing}"


@pytest.mark.parametrize("slug", sorted(TUTORIALS))
def test_avertissements_annonces(slug):
    """Le tutoriel nomme chaque paramètre que R34 signale sur son projet, et ne promet aucun blocage."""
    page = (GUIDE / f"{slug}.md").read_text(encoding="utf-8")
    diags = ENGINE.evaluate(build_starter(TUTORIALS[slug], CATALOG))
    assert not [d for d in diags if d.severity.value == "bloquant"]
    for d in diags:
        if d.rule_id == "R34":
            label = re.search(r"« ([^»]+) » non renseigné", d.message).group(1)
            assert label in page, f"{slug}.md ne mentionne pas « {label} » ({d.message})"


def test_captures_du_guide_presentes():
    for slug in TUTORIALS:
        assert (ROOT / "docs" / "guide" / "captures" / f"{slug}.png").exists()
