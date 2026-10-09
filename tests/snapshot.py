"""Instantanés de non-régression : ce que l'application génère pour un corpus fixe de projets.

    python tests/snapshot.py sortie/      écrit un instantané (un dossier par projet)

Le corpus réunit les exemples livrés, la matrice des tests de génération et un échantillon
déterministe des combinaisons de l'assistant. Pour chaque projet : tous les fichiers
générés (date du rapport neutralisée) et les diagnostics des règles. tests/test_regression.py
compare la génération courante à l'instantané enregistré dans tests/golden/.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from devops_builder.catalog import build_catalog  # noqa: E402
from devops_builder.generators import generate  # noqa: E402
from devops_builder.model import Project  # noqa: E402
from devops_builder.rules import RuleEngine  # noqa: E402

EXAMPLES = HERE.parent / "devops_builder" / "data" / "examples"
GOLDEN = HERE / "golden"
WIZARD_STEP = 97  # une combinaison de l'assistant sur 97 (≈ 50 projets)
LEGACY_ENV_PRESETS = ("prod", "staging-prod", "dev-staging-prod")
DATE = re.compile(r"le \d{4}-\d{2}-\d{2}\.")
UID = re.compile(r"\buid: '?[0-9a-f]{8}'?")


def _stable_uids(text: str) -> str:
    """Les identifiants de briques sont aléatoires : numérotés dans l'ordre pour l'instantané."""
    counter = iter(range(1, 10_000))
    return UID.sub(lambda _m: f"uid: brique{next(counter):03d}", text)


def corpus() -> dict[str, Project]:
    from test_generators import MATRIX
    from test_starter import all_answers

    from devops_builder.starter import build_starter
    catalog = packaged_catalog()
    cases: dict[str, Project] = {}
    for path in sorted(EXAMPLES.glob("*.devops.yaml")):
        cases[f"exemple-{path.name.split('.')[0]}"] = Project.load(path)
    for name, p in MATRIX.items():
        cases[f"matrice-{name}"] = p
    # Échantillon historique : seulement les modèles d'environnements de la 0.4, pour que
    # l'ajout d'un modèle ne décale pas la numérotation des cas déjà figés.
    legacy = [a for a in all_answers() if a.envs in LEGACY_ENV_PRESETS]
    for i, answers in enumerate(legacy):
        if i % WIZARD_STEP == 0:
            cases[f"assistant-{i:04d}"] = build_starter(answers, catalog)
    for name, project in extra_cases(catalog).items():
        cases[name] = project
    return cases


def extra_cases(catalog) -> dict[str, Project]:
    """Cas ajoutés après la 0.4 : un par fonctionnalité qui change les fichiers générés."""
    from devops_builder.starter import StarterAnswers, build_starter
    out: dict[str, Project] = {}
    try:
        from devops_builder.model import ENV_PRESETS
    except ImportError:  # pragma: no cover
        return out
    for preset in ENV_PRESETS:
        if preset in LEGACY_ENV_PRESETS:
            continue
        for hosting, cloud in (("docker-host", None), ("kubernetes", None), ("kubernetes-managed", "aws")):
            a = StarterAnswers(forge="gitlab", hosting=hosting, cloud=cloud, envs=preset, gitops=False)
            out[f"envs-{preset}-{hosting}"] = build_starter(a, catalog)
    # hôte Docker partagé par les environnements hors production : ports décalés
    shared = build_starter(StarterAnswers(forge="gitlab", hosting="docker-host", envs="dev-staging-prod"), catalog)
    for env in shared.environments:
        if env.kind != "production" and hasattr(env, "host"):
            env.host = "vm-hors-prod"
    out["ports-hote-partage"] = shared
    return out


_CATALOG = None


def packaged_catalog():
    """Catalogue livré seul : un catalogue utilisateur ne doit pas changer l'instantané."""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = build_catalog(user_dir=None)
    return _CATALOG


def render_case(project: Project) -> dict[str, str]:
    catalog = packaged_catalog()
    engine = RuleEngine(catalog)
    diags = engine.evaluate(project)
    lines = [f"{d.severity.value} {d.rule_id} {d.message}" for d in diags]
    out = {"_diagnostics.txt": "\n".join(sorted(lines)) + "\n"}
    if RuleEngine.blocking(diags):
        return out
    result = generate(project, catalog, engine)
    for rel, content in result.files.items():
        content = DATE.sub("le AAAA-MM-JJ.", content) if rel == "PIPELINE.md" else content
        out[rel] = _stable_uids(content) if rel == "devops-builder.yaml" else content
    return out


def write_snapshot(root: Path) -> int:
    count = 0
    for name, project in corpus().items():
        for rel, content in render_case(project).items():
            path = root / name / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            count += 1
    return count


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else GOLDEN
    print(f"{write_snapshot(target)} fichiers écrits dans {target}")
