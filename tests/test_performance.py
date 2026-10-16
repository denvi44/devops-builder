# SPDX-License-Identifier: Apache-2.0
"""Performances sur un gros projet : toutes les fiches vérifiées, cinq environnements.

Les règles sont réévaluées à chaque modification du projet (R31 rend tous les fichiers) : sur le poste de
développement, 0,07 s pour évaluer et 0,17 s pour générer les 167 briques ; les seuils laissent la marge
d'une machine de CI lente.
"""

from __future__ import annotations

import time

import yaml

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.model import Project, env_preset
from devops_builder.rules import RuleEngine

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)


def big_project() -> Project:
    p = Project(name="Gros projet", target="kubernetes")
    p.environments = env_preset("complet")
    for tool in CATALOG.curated():
        if not p.bricks_for(tool.id):
            p.add(tool.id, tool.stage)
    return p


def best_of(fn, n: int = 3) -> float:
    times = []
    for _ in range(n):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return min(times)


def test_libyaml_disponible():
    # sans l'émetteur C, tout est trois à cinq fois plus lent (paquet PyYAML construit sans libyaml)
    assert yaml.__with_libyaml__


def test_gros_projet_evalue_et_genere_vite():
    p = big_project()
    assert len([b for bricks in p.stages.values() for b in bricks]) > 150
    assert best_of(lambda: ENGINE.evaluate(p)) < 1.0
    assert best_of(lambda: generate(p, CATALOG, ENGINE, allow_blocking=True)) < 2.0
    assert best_of(lambda: Project.from_yaml(p.to_yaml())) < 0.3
