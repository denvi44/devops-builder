# SPDX-License-Identifier: Apache-2.0
"""Matrice publique de prise en charge : ce que les générateurs savent faire de chaque fiche.

    python -m devops_builder.support > docs/prise-en-charge.md
"""

from __future__ import annotations

from .catalog import Catalog, default_catalog
from .model import STAGE_IDS, STAGE_LABELS, SUPPORT

CRITERIA = {
    "supported": "les fichiers sont générés et passent l'outil de référence dans les tests (linter, schéma, "
                 "`tofu validate`, ShellCheck) ; aucune limite connue n'empêche le premier déploiement "
                 "en suivant `docs/mise-en-route.md`.",
    "experimental": "les fichiers sont générés, mais une limite connue demande une intervention ou n'a pas "
                    "été vérifiée ; la règle R50 la rappelle dans le projet.",
    "manual": "aucun générateur ne produit de fichier ; la brique sert aux règles et à la documentation, "
              "elle est listée dans « À configurer à la main » de `PIPELINE.md` (règle R31).",
}


def matrix_markdown(catalog: Catalog) -> str:
    tools = sorted(catalog.curated(), key=lambda t: (STAGE_IDS.index(t.stage), t.name.lower()))
    tools = [t for t in tools if t.origin == "livrée"]
    counts = {k: sum(1 for t in tools if t.support == k) for k in SUPPORT}
    out = ["# Prise en charge des briques", "",
           "Fichier produit par `python -m devops_builder.support` ; un test vérifie qu'il est à jour, "
           "et un autre que chaque niveau correspond à ce que les générateurs produisent.", "",
           "## Niveaux", ""]
    out += [f"- **{SUPPORT[k]}** ({counts[k]}) : {CRITERIA[k]}" for k in SUPPORT]
    out += ["", "Une entrée du CNCF Landscape sans fiche, ou une fiche personnelle, est toujours à configurer "
            "à la main.", ""]
    for level in ("experimental", "manual"):
        out += [f"## {SUPPORT[level]}", "", "| Brique | Étape | Raison |", "| --- | --- | --- |"]
        out += [f"| {t.name} | {STAGE_LABELS[t.stage]} | {t.support_note} |" for t in tools if t.support == level]
        out.append("")
    out += ["## Pris en charge", ""]
    for sid in STAGE_IDS:
        names = [t.name for t in tools if t.stage == sid and t.support == "supported"]
        if names:
            out.append(f"- **{STAGE_LABELS[sid]}** : {', '.join(names)}")
    out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    print(matrix_markdown(default_catalog()), end="")
