# SPDX-License-Identifier: Apache-2.0
"""Interface en ligne de commande (sans interface graphique).

    python -m devops_builder                      # lance l'interface graphique
    python -m devops_builder check projet.devops.yaml
    python -m devops_builder generate projet.devops.yaml -o sortie/ [--dry-run] [--overwrite] [--force]
    python -m devops_builder validate projet.devops.yaml [--offline]
    python -m devops_builder test-kind projet.devops.yaml [--env dev] [--app-dir ../code] [--keep]
    python -m devops_builder export-git projet.devops.yaml --repo ../depot [--branch …] [--no-push]
    python -m devops_builder catalog-check [--offline] [--apply] [--report rapport.md]
    python -m devops_builder catalog-import "Nom dans le Landscape" [--id …] [--stage …]
    python -m devops_builder landscape-refresh [--source landscape.yml] [--reset]
    python -m devops_builder scan ../mon-app [--json]
    python -m devops_builder init ../mon-app -o mon-app.devops.yaml [--hosting …] [--envs …]

Codes de sortie (contrat stable, voir docs/ligne-de-commande.md) :
    0  succès
    1  problème trouvé : erreur bloquante, contrôle en échec, export impossible, fiche à corriger
    2  utilisation incorrecte ou fichier projet illisible
    test-kind rend le code de sortie du script de test.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__, sync
from .catalog import default_catalog
from .generators import BlockingDiagnostics, GenerationResult, generate
from .messages import explain
from .model import Project, ProjectFormatError
from .rules import RuleEngine

OK, PROBLEM, USAGE = 0, 1, 2
JSON_SCHEMA = 1  # version de la sortie --json : un champ retiré ou renommé l'augmente


def _diag_json(d) -> dict:
    return {"rule": d.rule_id, "severity": d.severity.value, "family": d.family, "message": d.message,
            "bricks": list(d.bricks), "actions": [a.label for a in d.actions]}


def _emit(command: str, ok: bool, **data) -> None:
    import json
    print(json.dumps({"schema": JSON_SCHEMA, "command": command, "version": __version__, "ok": ok, **data},
                     ensure_ascii=False, indent=2))


def _load_project(path: str) -> Project | None:
    """Fichier absent ou illisible : message sur la sortie d'erreur, None (code 2)."""
    try:
        return Project.load(path)
    except FileNotFoundError:
        print(f"Fichier projet introuvable : {path}", file=sys.stderr)
    except ProjectFormatError as exc:
        print(f"Fichier projet illisible : {path} : {exc}", file=sys.stderr)
    except OSError as exc:
        print(f"Fichier projet illisible : {explain(exc, path)}", file=sys.stderr)
    return None


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
    # sortie redirigée sous Windows (cp1252) : un caractère hors de la page de code ne doit pas tout arrêter
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(prog="devops-builder", description="Composer des pipelines DevOps cohérents.",
                                     epilog="Codes de sortie : 0 succès, 1 problème trouvé, 2 utilisation ou fichier "
                                            "illisible.")
    parser.add_argument("--version", action="version", version=f"devops-builder {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="Vérifier un projet")
    c.add_argument("project")
    c.add_argument("--json", action="store_true", help="Sortie JSON (diagnostics)")
    g = sub.add_parser("generate", help="Générer les fichiers d'un projet dans un dossier")
    g.add_argument("project")
    g.add_argument("-o", "--output", required=True)
    g.add_argument("--force", action="store_true", help="Générer malgré les erreurs bloquantes")
    g.add_argument("--dry-run", action="store_true", help="Afficher les changements sans rien écrire")
    g.add_argument("--json", action="store_true", help="Sortie JSON (fichiers et leur état)")
    g.add_argument("--overwrite", action="store_true",
                   help="Remplacer aussi les fichiers retouchés à la main ou étrangers à DevOps Builder")
    v = sub.add_parser("validate", help="Contrôler les fichiers générés avec les outils installés")
    v.add_argument("project")
    v.add_argument("--offline", action="store_true", help="Sauter les contrôles qui téléchargent des schémas")
    v.add_argument("-v", "--verbose", action="store_true", help="Afficher la sortie de chaque contrôle")
    v.add_argument("--json", action="store_true", help="Sortie JSON (résultat de chaque contrôle)")
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
    cc = sub.add_parser("catalog-check", help="Entretien du catalogue : archivage, licences, fiches à relire")
    cc.add_argument("--offline", action="store_true", help="Ne pas interroger GitHub ni GitLab")
    cc.add_argument("--refresh", action="store_true", help="Ignorer le cache des dépôts (24 h)")
    cc.add_argument("--apply", action="store_true",
                    help="Appliquer les corrections proposées (archivage, licence, adresse du dépôt)")
    cc.add_argument("--report", help="Écrire le rapport Markdown dans ce fichier")
    ci = sub.add_parser("catalog-import", help="Créer une fiche personnelle à partir d'une entrée du Landscape")
    ci.add_argument("name", help="Nom de l'entrée dans le Landscape")
    ci.add_argument("--id", help="Identifiant de la fiche (défaut : déduit du nom)")
    ci.add_argument("--stage", help="Étape principale (défaut : déduite de la sous-catégorie)")
    ci.add_argument("--license", help="Licence SPDX (défaut : lue sur le dépôt)")
    ci.add_argument("--offline", action="store_true", help="Ne pas lire la licence sur le dépôt")
    lr = sub.add_parser("landscape-refresh", help="Télécharger le Landscape à jour et reconstruire l'index")
    lr.add_argument("--source", help="Fichier ou URL de landscape.yml (défaut : dépôt cncf/landscape)")
    lr.add_argument("--reset", action="store_true", help="Revenir à l'index livré avec l'application")
    sc = sub.add_parser("scan", help="Analyser le dossier d'une application")
    sc.add_argument("folder")
    sc.add_argument("--json", action="store_true", help="Sortie JSON")
    tp = sub.add_parser("template", help="Créer un projet depuis un pipeline type par fournisseur cloud")
    tp.add_argument("modele", nargs="?", help="aws, gcp, azure, ovhcloud, scaleway, outscale, aws-ecs, aws-ec2… ; sans argument : la liste")
    tp.add_argument("-o", "--output", help="Fichier projet à écrire (.devops.yaml)")
    it = sub.add_parser("init", help="Créer un projet à partir du dossier d'une application")
    it.add_argument("folder")
    it.add_argument("-o", "--output", required=True, help="Fichier projet à écrire (.devops.yaml)")
    it.add_argument("--hosting", help="Hébergement : docker-host, vm, kubernetes, kubernetes-managed, serverless")
    it.add_argument("--cloud", help="Cloud pour kubernetes-managed ou serverless (aws, gcp, azure…)")
    it.add_argument("--database", choices=["none", "postgresql", "mysql", "mariadb", "mongodb"],
                    help="Base de données principale (par défaut : celle que l'analyse a détectée)")
    it.add_argument("--envs", default="staging-prod", help="Modèle d'environnements (prod, staging-prod, …)")
    raw = sys.argv[1:] if argv is None else argv
    if raw and raw[0].endswith((".yaml", ".yml")) and not raw[0].startswith("-"):
        # « devops-builder projet.devops.yaml » (ou un double-clic sur le fichier) : l'ouvrir dans l'interface
        from .ui.app import run
        return run(["devops-builder", *raw])
    args = parser.parse_args(argv)

    if args.cmd in ("scan", "init"):
        return _app_command(args)
    if args.cmd == "template":
        return _template_command(args)
    if args.cmd is None:
        from .ui.app import run
        return run()
    if args.cmd in ("catalog-check", "catalog-import", "landscape-refresh"):
        return _catalog_command(args)

    project = _load_project(args.project)
    if project is None:
        return USAGE
    as_json = getattr(args, "json", False)
    unknown = project.unknown_fields()
    if unknown and not as_json:
        print(f"Champs inconnus de cette version, conservés : {', '.join(unknown)}", file=sys.stderr)
    catalog = default_catalog()
    engine = RuleEngine(catalog)
    if args.cmd == "check":
        diags = engine.evaluate(project)
        blocking = RuleEngine.blocking(diags)
        if as_json:
            _emit("check", not blocking, project=args.project, blocking=len(blocking),
                  diagnostics=[_diag_json(d) for d in diags], unknown_fields=unknown)
        else:
            _print_diags(diags)
        return PROBLEM if blocking else OK
    try:
        result = generate(project, catalog, engine, allow_blocking=getattr(args, "force", False))
    except BlockingDiagnostics as exc:
        if as_json:
            _emit(args.cmd, False, project=args.project, error="erreurs bloquantes",
                  diagnostics=[_diag_json(d) for d in exc.diagnostics], unknown_fields=unknown)
        else:
            print("Génération refusée : erreurs bloquantes.")
            _print_diags(exc.diagnostics)
        return PROBLEM

    if args.cmd == "generate":
        try:
            changes = sync.plan(result.files, args.output)
            _select(changes, args.overwrite)
            touched = [] if args.dry_run else sync.apply(changes, args.output)
        except OSError as exc:
            message = f"Écriture impossible dans « {args.output} » : {exc.strerror or exc}."
            if as_json:
                _emit("generate", False, project=args.project, error=message)
            else:
                print(message, file=sys.stderr)
            return USAGE
        kept = [c.path for c in changes if c.status in (sync.EDITED, sync.FOREIGN) and not c.selected]
        if as_json:
            files = []
            for c in changes:
                added, removed = c.stats()
                files.append({"path": c.path, "status": c.status, "selected": c.selected, "deletion": c.deletion,
                              "added": added, "removed": removed})
            _emit("generate", True, project=args.project, output=args.output, dry_run=args.dry_run,
                  written=len([t for t in touched if t != sync.MANIFEST]), kept=kept, files=files,
                  unsupported=[t.id for t in result.ir.unsupported], unknown_fields=unknown)
            return OK
        if args.dry_run:
            _print_plan(changes)
            return OK
        print(f"{len([t for t in touched if t != sync.MANIFEST])} fichier(s) écrit(s) dans {args.output} "
              f"({sync.describe(changes)}).")
        _skipped_hint(changes)
        return OK

    if args.cmd == "validate":
        from .validate import FAILED, summary, validate_files
        marks = {"ok": "✓", "échec": "✗", "absent": "·", "ignoré": "–"}

        def show(r):
            print(f"{marks.get(r.status, '?')} {r.label:52} {r.status}" + (f" ({r.seconds:.1f} s)" if r.seconds else ""))
            if r.output and (args.verbose or r.status == FAILED):
                print("    " + r.output.replace("\n", "\n    "))
        results = validate_files(result.files, network=not args.offline, on_result=None if as_json else show)
        failed = any(r.failed for r in results)
        if as_json:
            _emit("validate", not failed, project=args.project, summary=summary(results),
                  results=[{"id": r.id, "label": r.label, "status": r.status, "files": r.files,
                            "seconds": round(r.seconds, 2), "output": r.output, "hint": r.hint} for r in results])
        else:
            print(summary(results))
        return PROBLEM if failed else OK

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


def _app_command(args) -> int:
    import json

    from . import appscan
    from .starter import StarterAnswers, answers_from_profile, build_starter, validate
    try:
        profile = appscan.scan(args.folder)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return USAGE
    if args.cmd == "scan":
        if args.json:
            print(json.dumps(appscan.to_json(profile), ensure_ascii=False, indent=2))
        else:
            print(f"{profile.path} : {profile.image_name}")
            for line in profile.summary():
                print(f"  · {line}")
        return 0
    catalog = default_catalog()
    base = StarterAnswers(envs=args.envs)
    answers, taken = answers_from_profile(profile, catalog, base)
    if args.hosting:
        answers.hosting = args.hosting
    if args.cloud:
        answers.cloud = args.cloud
    if args.database:
        answers.database = args.database
    problems = validate(answers)
    if problems:
        print("Réponses incomplètes : " + " ".join(problems) + " (préciser --hosting/--cloud).")
        return 1
    project = build_starter(answers, catalog)
    project.save(args.output)
    print(f"Projet écrit dans {args.output} ; repris de l'analyse : {', '.join(taken)}.")
    diags = RuleEngine(catalog).evaluate(project)
    blocking = RuleEngine.blocking(diags)
    print(f"{len(project.all_bricks())} briques, {len(diags)} diagnostic(s)" + (f", dont {len(blocking)} bloquant(s)" if blocking else "") + ".")
    return 1 if blocking else 0


def _template_command(args) -> int:
    from .modeles import MODELES, build
    if not args.modele:
        for m in MODELES.values():
            print(f"{m.slug:<10} {m.title} — {m.description}")
        return 0
    if args.modele not in MODELES:
        print(f"Modèle inconnu : {args.modele} (au choix : {', '.join(MODELES)})", file=sys.stderr)
        return USAGE
    if not args.output:
        print("Préciser le fichier à écrire : -o projet.devops.yaml", file=sys.stderr)
        return USAGE
    catalog = default_catalog()
    project = build(args.modele, catalog)
    project.save(args.output)
    diags = RuleEngine(catalog).evaluate(project)
    print(f"Projet « {project.name} » écrit dans {args.output} : {len(project.all_bricks())} briques, "
          f"{len(diags)} valeur(s) à renseigner ou diagnostic(s) (devops-builder check {args.output}).")
    return 0


def _catalog_command(args) -> int:
    from . import catalog_edit, health, landscape, userdata
    from .catalog import reload_default_catalog

    if args.cmd == "landscape-refresh":
        if args.reset:
            print("Index livré rétabli." if landscape.reset() else "Aucun index personnel : l'index livré est déjà utilisé.")
            return 0
        try:
            diff, path = landscape.refresh(args.source)
        except Exception as exc:  # réseau, fichier, format
            print(f"Rafraîchissement impossible : {explain(exc)}")
            return 1
        print(f"Index écrit dans {path} : {diff.summary()}.")
        catalog = reload_default_catalog()
        touched = [t for t in catalog.curated() if t.landscape_name in diff.newly_archived or t.name in diff.newly_archived]
        for t in touched:
            print(f"  ! {t.name} : nouvellement archivé dans le Landscape — lancer catalog-check")
        return 0

    catalog = reload_default_catalog()
    if args.cmd == "catalog-import":
        entries = landscape.load_index(catalog.index_path)
        entry = next((e for e in entries if e["name"].lower() == args.name.lower()), None)
        if entry is None:
            import difflib
            close = difflib.get_close_matches(args.name, [e["name"] for e in entries], n=5, cutoff=0.5)
            print(f"« {args.name} » est absent de l'index du Landscape."
                  + (f" Noms proches : {', '.join(close)}." if close else ""))
            return 1
        known = next((t for t in catalog.curated() if (t.landscape_name or t.name).lower() == entry["name"].lower()), None)
        if known:
            print(f"« {entry['name']} » a déjà une fiche : {known.id} ({known.origin}).")
            return 1
        data = catalog_edit.draft_from_landscape(entry, catalog)
        if args.id:
            data["id"] = args.id
        if args.stage:
            data["stage"] = args.stage
        if args.license:
            data["license"] = args.license
        elif not args.offline:
            data["license"] = catalog_edit.license_from_repo(data.get("repo")) or "unknown"
        try:
            path = catalog_edit.save_fiche(data, catalog)
        except ValueError as exc:
            print(f"Fiche refusée : {exc}")
            return 1
        print(f"Fiche « {data['id']} » écrite dans {path} (étape {data['stage']}, licence {data['license']}).")
        print("À relire : rôles, capacités fournies et requises, cibles d'hébergement.")
        return 0

    marks = {health.TO_FIX: "✗", health.WATCH: "!", health.INFO: "·"}

    def progress(done: int, total: int) -> None:
        if total:
            print(f"\r  dépôts : {done}/{total}", end="", flush=True)
    report = health.check_catalog(catalog, network=not args.offline, refresh=args.refresh,
                                  progress=None if args.offline else progress)
    if not args.offline:
        print()
    print(f"Catalogue : {len(catalog.curated())} fiches ({len(catalog.user_tools())} personnelles), "
          f"dossier personnel {userdata.catalog_dir()}")
    for f in report.findings:
        fix = f"  → {f.fix_label}" if f.fix else ""
        print(f"{marks[f.level]} [{f.level}] {f.tool_name} : {f.message}{fix}")
    print(report.summary() + ".")
    if args.report:
        Path(args.report).write_text(report.markdown(), encoding="utf-8")
        print(f"Rapport écrit dans {args.report}")
    if args.apply:
        fixes = [(f.tool_id, f.fix) for f in report.findings if f.fix and f.kind != "stale"]
        changed = catalog_edit.apply_fixes(fixes, catalog)
        print(f"{len(changed)} correction(s) appliquée(s)" + (f" : {', '.join(changed)}" if changed else "") + ".")
        return 0
    return 1 if report.by_level(health.TO_FIX) else 0


if __name__ == "__main__":
    sys.exit(main())
