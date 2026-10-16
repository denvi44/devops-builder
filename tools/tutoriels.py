# SPDX-License-Identifier: Apache-2.0
"""Projets des tutoriels du guide (docs/guide/tutoriels/) : les réponses données à l'assistant.

Les captures du guide (tools/screenshot.py) et le test qui confronte chaque tutoriel aux fichiers
réellement générés (tests/test_guide.py) partent de ces réponses : le guide ne peut pas décrire un
pipeline que l'application ne produit plus.
"""

from __future__ import annotations

from devops_builder.starter import StarterAnswers

TUTORIALS: dict[str, StarterAnswers] = {
    "hote-docker": StarterAnswers(name="Boutique", language="python", image_name="boutique", port=8000,
                                  forge="gitlab", hosting="docker-host", envs="staging-prod", database="postgresql"),
    "k3s-gitops": StarterAnswers(name="API commandes", language="node", image_name="api-commandes", port=3000,
                                 forge="github", hosting="kubernetes", envs="dev-staging-prod", gitops=True),
    "eks": StarterAnswers(name="Plateforme", language="java", image_name="plateforme", port=8080, forge="gitlab",
                          hosting="kubernetes-managed", cloud="aws", envs="staging-prod", database="postgresql",
                          secrets="cloud"),
    "souverain": StarterAnswers(name="Téléservice", language="python", image_name="teleservice", port=8000,
                                forge="gitlab", hosting="vm", cloud="outscale", secnumcloud=True, envs="staging-prod",
                                database="postgresql", secrets="sops"),
}
