"""Interface en ligne de commande (sans interface graphique).

    python -m devops_builder                      # lance l'interface graphique
    python -m devops_builder check projet.devops.yaml
    python -m devops_builder generate projet.devops.yaml -o sortie/ [--force]
"""

from __future__ import annotations

import argparse
import sys

from .catalog import default_catalog
from .generators import BlockingDiagnostics, generate
from .model import Project
from .rules import RuleEngine


def _print_diags(diags) -> None:
    for d in diags:
        print(f"[{d.severity.label:13}] {d.rule_id} {d.message}")
        for a in d.actions:
            print(f"                 → {a.label}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="devops-builder", description="Composer des pipelines DevOps cohérents.")
    sub = parser.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="Vérifier un projet")
    c.add_argument("project")
    g = sub.add_parser("generate", help="Générer les fichiers d'un projet")
    g.add_argument("project")
    g.add_argument("-o", "--output", required=True)
    g.add_argument("--force", action="store_true", help="Générer malgré les erreurs bloquantes")
    args = parser.parse_args(argv)

    if args.cmd is None:
        from .ui.app import run
        return run()

    catalog = default_catalog()
    project = Project.load(args.project)
    engine = RuleEngine(catalog)
    if args.cmd == "check":
        diags = engine.evaluate(project)
        _print_diags(diags)
        return 1 if RuleEngine.blocking(diags) else 0
    try:
        result = generate(project, catalog, engine, allow_blocking=args.force)
    except BlockingDiagnostics as exc:
        print("Génération refusée : erreurs bloquantes.")
        _print_diags(exc.diagnostics)
        return 1
    written = result.write(args.output)
    print(f"{len(written)} fichiers écrits dans {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
