# SPDX-License-Identifier: Apache-2.0
"""Tests de bout en bout : les fichiers générés, exécutés pour de vrai (lot 0.17).

    python tools/e2e/run.py --list                 scénarios disponibles
    python tools/e2e/run.py kind-helm-cnpg         lance un scénario (Docker, kind, kubectl, helm requis)
    python tools/e2e/run.py compose-postgresql --plan   affiche les étapes sans rien exécuter

Chaque scénario construit un projet avec l'API de l'application, génère ses fichiers dans un dossier
jetable, puis exécute ce qu'un utilisateur exécuterait : scripts générés, docker compose, kubectl.
L'application déployée est tools/e2e/app : elle répond 200 sur /db seulement si chaque base accepte une
connexion authentifiée avec les secrets que le pipeline lui a transmis.

Le rapport (étapes, durées, sortie des échecs) est écrit sur la sortie standard et, dans GitHub Actions,
dans le résumé du job ($GITHUB_STEP_SUMMARY). Code de sortie : 0 si tout passe, 1 sinon, 2 si usage.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from devops_builder.catalog import build_catalog  # noqa: E402
from devops_builder.generators import generate  # noqa: E402
from devops_builder.model import Project, env_preset  # noqa: E402
from devops_builder.rules import RuleEngine  # noqa: E402

APP_DIR = HERE / "app"
APP = "boutique"
GH = ("github", "github-actions", "buildkit", "ghcr")


@dataclass
class Step:
    name: str
    command: list[str] | str            # liste : exécutée telle quelle ; texte : par bash -euo pipefail
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    retries: int = 1                     # tentatives (attente d'un service)
    always: bool = False                 # nettoyage : exécutée même après un échec


@dataclass
class Result:
    step: Step
    ok: bool
    seconds: float
    output: str


@dataclass
class Scenario:
    name: str
    description: str
    project: Callable[[], Project]
    steps: Callable[[Path, object], list[Step]]   # (dossier généré, IR) → étapes
    tools: tuple[str, ...]


def _project(target: str, *tools: str, envs: str = "prod", **params) -> Project:
    p = Project(name="Boutique e2e", target=target, environments=env_preset(envs))
    p.app.image_name, p.app.port = APP, 8000
    catalog = _catalog()
    for t in tools:
        p.add(t, catalog[t].stage, **params.get(t.replace("-", "_"), {}))
    return p


_CAT = None


def _catalog():
    global _CAT
    if _CAT is None:
        _CAT = build_catalog(user_dir=None)
    return _CAT


# ------------------------------------------------------------------ Kubernetes (kind)
def _kind_steps(out: Path, ir) -> list[Step]:
    env = ir.envs[0]
    ns = ir.namespace(env)
    cluster = f"{ir.app}-test"[:40]
    ctx = f"kind-{cluster}"
    image = f"devops-builder.local/{ir.app}:e2e"
    check_db = f"""
kubectl --context {ctx} -n {ns} port-forward service/{ir.app} 18081:80 >/tmp/pf.log 2>&1 &
pf=$!
trap 'kill $pf 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  code=$(curl -s -o /tmp/db.json -w '%{{http_code}}' http://127.0.0.1:18081/db || true)
  [ "$code" = 200 ] && {{ cat /tmp/db.json; exit 0; }}
  sleep 2
done
echo "réponse $code :"; cat /tmp/db.json 2>/dev/null || true
kubectl --context {ctx} -n {ns} logs deployment/{ir.app} --tail=40 || true
exit 1
"""
    return [
        Step("Image de l'application de démonstration", ["docker", "build", "-t", image, str(APP_DIR)]),
        Step("scripts/test-kind.sh : cluster, chart ou overlay, rollout, réponse HTTP",
             ["bash", "scripts/test-kind.sh", env.id], cwd=out, env={"IMAGE": image, "KEEP_CLUSTER": "1"}),
        Step("Connexion authentifiée aux bases depuis le pod (/db)", check_db, cwd=out),
        Step("État du cluster", f"kubectl --context {ctx} get pods -A -o wide", always=True),
        Step("Suppression du cluster", ["kind", "delete", "cluster", "--name", cluster], always=True),
    ]


# ------------------------------------------------------------------ hôte Docker (Compose)
def _compose_steps(out: Path, ir) -> list[Step]:
    host = out.parent / "opt" / ir.app        # disposition d'un hôte réel : /opt/<application>
    backups = out.parent / "sauvegardes"
    image = f"devops-builder.local/{ir.app}:e2e"
    password = secrets.token_hex(12)
    env = {"POSTGRESQL_PASSWORD": password, "VALKEY_PASSWORD": secrets.token_hex(12), "IMAGE": image}
    dc = f"docker compose --project-directory {host} -p {ir.app}"
    probe = (f"{dc} exec -T {ir.app} python -c \"import sys,urllib.request as u;"
             "r=u.urlopen('http://127.0.0.1:8000/db',timeout=10);print(r.read().decode());"
             "sys.exit(0 if r.status==200 else 1)\"")
    psql = f"{dc} exec -T postgresql sh -c 'psql -v ON_ERROR_STOP=1 -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -tA'"

    def sql(statement: str) -> str:  # requête par l'entrée standard : pas de guillemets imbriqués
        return f"{psql} <<'SQL'\n{statement}\nSQL"
    return [
        Step("Image de l'application de démonstration", ["docker", "build", "-t", image, str(APP_DIR)]),
        Step("Fichiers posés comme sur l'hôte (/opt/<application>)",
             f"mkdir -p {host} && cp -R {out}/deploy/. {host}/ && ls -la {host}"),
        Step("deploy/secrets.sh : fichiers de secrets", ["sh", "secrets.sh", "secrets"], cwd=host, env=env),
        Step("docker compose up (santé des services attendue)", f"{dc} up -d --wait --wait-timeout 180",
             cwd=host, env=env),
        Step("Connexion authentifiée aux bases depuis l'application (/db)", probe, retries=10, env=env),
        Step("Donnée témoin écrite", sql("create table temoin(v text); insert into temoin values ('avant');"),
             env=env),
        Step("scripts/db-backup.sh", ["sh", str(out / "scripts" / "db-backup.sh"), str(host), str(backups)], env=env),
        Step("Donnée témoin modifiée après la sauvegarde", sql("update temoin set v = 'apres';"), env=env),
        Step("scripts/db-restore.sh refuse sans --oui",
             f"! sh {out}/scripts/db-restore.sh {host} \"$(ls {backups}/postgresql-*.dump | head -n 1)\"", env=env),
        Step("scripts/db-restore.sh --oui",
             f"sh {out}/scripts/db-restore.sh {host} \"$(ls {backups}/postgresql-*.dump | head -n 1)\" --oui", env=env),
        Step("Donnée témoin revenue à l'état sauvegardé",
             f"v=$({sql('select v from temoin;')}\n)\necho \"valeur : $v\"\ntest \"$v\" = avant", env=env),
        Step("Journaux des services", f"{dc} ps -a; {dc} logs --tail=30", always=True, env=env),
        Step("Arrêt et suppression des volumes", f"{dc} down -v --remove-orphans", always=True, env=env),
    ]


SCENARIOS = {s.name: s for s in [
    Scenario("kind-helm-cnpg", "k3s + chart Helm + PostgreSQL par CloudNativePG, dans kind",
             lambda: _project("kubernetes", *GH, "k3s", "helm", "cloudnative-pg"),
             _kind_steps, ("docker", "kind", "kubectl", "helm", "curl")),
    Scenario("kind-kustomize-postgresql", "k3s + overlays Kustomize + PostgreSQL et Valkey en StatefulSet",
             lambda: _project("kubernetes", "gitlab", "gitlab-ci", "buildkit", "k3s", "kustomize", "postgresql",
                              "valkey"),
             _kind_steps, ("docker", "kind", "kubectl", "curl")),
    Scenario("compose-postgresql", "Hôte Docker : Compose, PostgreSQL, Valkey, sauvegarde puis restauration",
             lambda: _project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "traefik",
                              "postgresql", "valkey"),
             _compose_steps, ("docker",)),
]}


# ------------------------------------------------------------------ exécution
def prepare(scenario: Scenario, work: Path):
    """Projet construit, contrôlé (aucune erreur bloquante) et généré dans work/projet."""
    catalog = _catalog()
    project = scenario.project()
    blocking = RuleEngine.blocking(RuleEngine(catalog).evaluate(project))
    if blocking:
        raise SystemExit(f"{scenario.name} : projet bloqué par les règles : {[d.message for d in blocking]}")
    result = generate(project, catalog)
    out = work / "projet"
    result.write(out)
    project.save(out / "devops-builder.yaml")
    return out, result.ir


def run_step(step: Step, timeout: int = 900) -> Result:
    env = {**os.environ, **step.env}
    cmd = step.command if isinstance(step.command, list) else ["bash", "-euo", "pipefail", "-c", step.command]
    start, output, ok = time.monotonic(), "", False
    for attempt in range(step.retries):
        try:
            p = subprocess.run(cmd, cwd=step.cwd, env=env, capture_output=True, text=True, timeout=timeout)
            output, ok = (p.stdout + p.stderr), p.returncode == 0
        except subprocess.TimeoutExpired as exc:
            output, ok = f"délai dépassé ({timeout} s)\n{exc.stdout or ''}{exc.stderr or ''}", False
        if ok:
            break
        if attempt + 1 < step.retries:
            time.sleep(6)
    return Result(step, ok, time.monotonic() - start, output)


def report(scenario: Scenario, results: list[Result], missing: list[str]) -> str:
    ok = not missing and all(r.ok for r in results)
    lines = [f"## {'✅' if ok else '❌'} {scenario.name}", "", scenario.description, ""]
    if missing:
        lines += [f"Outils absents : {', '.join(missing)}", ""]
    lines += ["| Étape | Résultat | Durée |", "| --- | --- | --- |"]
    lines += [f"| {r.step.name} | {'ok' if r.ok else '**échec**'} | {r.seconds:.0f} s |" for r in results]
    for r in results:
        if not r.ok:
            tail = "\n".join(r.output.strip().splitlines()[-60:])
            lines += ["", f"### Échec : {r.step.name}", "", "```", tail, "```"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tests de bout en bout des fichiers générés.")
    parser.add_argument("scenario", nargs="?")
    parser.add_argument("--list", action="store_true", help="Lister les scénarios")
    parser.add_argument("--plan", action="store_true", help="Générer et afficher les étapes sans les exécuter")
    parser.add_argument("--keep", help="Dossier de travail à conserver (défaut : dossier temporaire supprimé)")
    args = parser.parse_args(argv)
    if args.list or not args.scenario:
        for s in SCENARIOS.values():
            print(f"{s.name:28} {s.description}")
        return 0 if args.list else 2
    scenario = SCENARIOS.get(args.scenario)
    if scenario is None:
        print(f"Scénario inconnu : {args.scenario}", file=sys.stderr)
        return 2
    work = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix=f"e2e-{scenario.name}-"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        out, ir = prepare(scenario, work)
        steps = scenario.steps(out, ir)
        if args.plan:
            for i, s in enumerate(steps, 1):
                cmd = s.command if isinstance(s.command, str) else " ".join(s.command)
                print(f"{i:2}. {s.name}{' (toujours)' if s.always else ''}\n    {cmd.strip()[:300]}")
            return 0
        missing = [t for t in scenario.tools if shutil.which(t) is None]
        results: list[Result] = []
        failed = bool(missing)
        for step in steps:
            if failed and not step.always:
                continue
            print(f"==> {step.name}", flush=True)
            r = run_step(step)
            results.append(r)
            if not r.ok and not step.always:
                failed = True
        text = report(scenario, results, missing)
        print(text)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(text)
        return 1 if failed else 0
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
