"""Interface en ligne de commande (sans interface graphique).

    python -m devops_builder                      # lance l'interface graphique
    python -m devops_builder check projet.devops.yaml
    python -m devops_builder generate projet.devops.yaml -o sortie/ [--dry-run] [--overwrite] [--force]
    python -m devops_builder validate projet.devops.yaml [--offline]
    python -m devops_builder test-kind projet.devops.yaml [--env dev] [--app-dir ../code] [--keep]
    python -m devops_builder export-git projet.devops.yaml --repo ../depot [--branch …] [--no-push]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import sync
from .catalog import default_catalog
from .generators import BlockingDiagnostics, GenerationResult, generate
from .model import Project
from .rules import RuleEngine


def _print_diags(diags) -> None:
    for d in diags:
        print(f"[{d.severity.label:13}] {d.rule_id} {d.message}")
        for a in d.actions:
            print(f"                 → {a.label}")


def _print_plan(changes: list[sync.FileChange]) -> None:
    for c in changes:
        if c.status == sync.SAME:
            continue
        added, removed = c.stats()
        mark = "×" if not c.selected else "+" if c.status == sync.NEW else "−" if c.deletion else "~"
        print(f"  {mark} {c.path:55} {c.status:18} +{added} −{removed}")
    print(f"  {sync.describe(changes)}")


def _select(changes: list[sync.FileChange], overwrite: bool) -> None:
    if overwrite:
        for c in changes:
            if c.status in (sync.EDITED, sync.FOREIGN):
                c.selected = True


def _skipped_hint(changes: list[sync.FileChange]) -> None:
    kept = [c for c in changes if c.status in (sync.EDITED, sync.FOREIGN) and not c.selected]
    if kept:
        print(f"{len(kept)} fichier(s) existant(s) laissé(s) tel(s) quel(s) ; --overwrite pour les remplacer :")
        for c in kept:
            print(f"  {c.path} ({c.status})")


def run_kind_test(files: dict[str, str], env: str | None = None, app_dir: str | None = None,
                  keep: bool = False) -> int:
    """Écrit les fichiers dans un dossier temporaire et lance scripts/test-kind.sh en direct."""
    from .generators.localtest import KIND_TEST
    if KIND_TEST not in files:
        print("Ce pipeline ne déploie ni chart Helm ni overlay Kustomize : pas de test kind possible.")
        return 2
    with tempfile.TemporaryDirectory(prefix="devops-builder-kind-") as tmp:
        GenerationResult(files=files, ir=None).write(tmp)  # type: ignore[arg-type]
        envvars = dict(os.environ)
        if app_dir:
            envvars["APP_DIR"] = str(Path(app_dir).resolve())
        if keep:
            envvars["KEEP_CLUSTER"] = "1"
        args = ["bash", str(Path(tmp) / KIND_TEST)] + ([env] if env else [])
        return subprocess.call(args, env=envvars, cwd=tmp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="devops-builder", description="Composer des pipelines DevOps cohérents.")
    sub = parser.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="Vérifier un projet")
    c.add_argument("project")
    g = sub.add_parser("generate", help="Générer les fichiers d'un projet dans un dossier")
    g.add_argument("project")
    g.add_argument("-o", "--output", required=True)
    g.add_argument("--force", action="store_true", help="Générer malgré les erreurs bloquantes")
    g.add_argument("--dry-run", action="store_true", help="Afficher les changements sans rien écrire")
    g.add_argument("--overwrite", action="store_true",
                   help="Remplacer aussi les fichiers retouchés à la main ou étrangers à DevOps Builder")
    v = sub.add_parser("validate", help="Contrôler les fichiers générés avec les outils installés")
    v.add_argument("project")
    v.add_argument("--offline", action="store_true", help="Sauter les contrôles qui téléchargent des schémas")
    v.add_argument("-v", "--verbose", action="store_true", help="Afficher la sortie de chaque contrôle")
    k = sub.add_parser("test-kind", help="Déployer le pipeline dans un cluster kind jetable")
    k.add_argument("project")
    k.add_argument("--env", help="Environnement à tester (défaut : développement, ou le premier)")
    k.add_argument("--app-dir", help="Dossier du code de l'application (Dockerfile)")
    k.add_argument("--keep", action="store_true", help="Garder le cluster après le test")
    e = sub.add_parser("export-git", help="Committer les fichiers sur une nouvelle branche et ouvrir une demande de fusion")
    e.add_argument("project")
    e.add_argument("--repo", required=True, help="Copie de travail du dépôt de l'application")
    e.add_argument("--branch", help="Nom de la branche (défaut : devops-builder/AAAAMMJJ-HHMM)")
    e.add_argument("--message", help="Message de commit")
    e.add_argument("--remote", help="Dépôt distant (défaut : origin)")
    e.add_argument("--no-push", action="store_true", help="Committer sans pousser")
    e.add_argument("--no-request", action="store_true", help="Ne pas créer de demande de fusion")
    e.add_argument("--overwrite", action="store_true", help="Remplacer aussi les fichiers retouchés à la main")
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
        result = generate(project, catalog, engine, allow_blocking=getattr(args, "force", False))
    except BlockingDiagnostics as exc:
        print("Génération refusée : erreurs bloquantes.")
        _print_diags(exc.diagnostics)
        return 1

    if args.cmd == "generate":
        changes = sync.plan(result.files, args.output)
        _select(changes, args.overwrite)
        if args.dry_run:
            _print_plan(changes)
            return 0
        touched = sync.apply(changes, args.output)
        print(f"{len([t for t in touched if t != sync.MANIFEST])} fichier(s) écrit(s) dans {args.output} "
              f"({sync.describe(changes)}).")
        _skipped_hint(changes)
        return 0

    if args.cmd == "validate":
        from .validate import FAILED, summary, validate_files
        marks = {"ok": "✓", "échec": "✗", "absent": "·", "ignoré": "–"}

        def show(r):
            print(f"{marks.get(r.status, '?')} {r.label:52} {r.status}" + (f" ({r.seconds:.1f} s)" if r.seconds else ""))
            if r.output and (args.verbose or r.status == FAILED):
                print("    " + r.output.replace("\n", "\n    "))
        results = validate_files(result.files, network=not args.offline, on_result=show)
        print(summary(results))
        return 1 if any(r.failed for r in results) else 0

    if args.cmd == "test-kind":
        return run_kind_test(result.files, args.env, args.app_dir, args.keep)

    if args.cmd == "export-git":
        from . import gitexport
        try:
            info = gitexport.inspect(args.repo)
            changes = sync.plan(result.files, info.root)
            _select(changes, args.overwrite)
            opts = gitexport.ExportOptions(
                branch=args.branch or gitexport.default_branch_name(),
                message=args.message or f"Pipeline DevOps Builder : {project.name}",
                title=f"Pipeline DevOps Builder — {project.name}",
                description=gitexport.describe_changes(changes),
                push=not args.no_push, remote=args.remote, open_request=not args.no_request,
                forge=result.ir.forge.forge if result.ir.forge else None)
            out = gitexport.export(changes, info.root, opts, log=lambda m: print(f"→ {m}"))
        except gitexport.GitError as exc:
            print(f"Export impossible : {exc}")
            return 1
        print(f"Commit {out.commit} sur « {out.branch} » ({len(out.files)} fichier(s)).")
        for m in out.messages:
            print(m)
        if out.request_url:
            print(("Demande de fusion créée : " if out.request_created else "Créer la demande de fusion : ")
                  + out.request_url)
        _skipped_hint(changes)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
