"""Validation locale des fichiers générés, avec les outils installés sur le poste.

Chaque contrôle s'applique à une partie des fichiers. Quand l'outil manque, le
contrôle est marqué « absent » avec la façon de l'installer : la validation
n'échoue jamais pour cette raison. Les contrôles qui téléchargent des schémas ou
des providers sont marqués « réseau » et peuvent être sautés (hors ligne).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

OK, FAILED, MISSING, SKIPPED = "ok", "échec", "absent", "ignoré"

# Fichier généré → schéma intégré à check-jsonschema
SCHEMAS = {
    ".gitlab-ci.yml": "vendor.gitlab-ci",
    ".github/workflows/pipeline.yml": "vendor.github-workflows",
    ".gitea/workflows/pipeline.yml": "vendor.github-workflows",
    "azure-pipelines.yml": "vendor.azure-pipelines",
    "cloudbuild.yaml": "vendor.cloudbuild",
    ".woodpecker.yml": "vendor.woodpecker-ci",
    "deploy/docker-compose.yml": "vendor.compose-spec",
    "renovate.json": "vendor.renovate",
    ".github/dependabot.yml": "vendor.dependabot",
}
CRD_CATALOG = "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
TIMEOUT = 180
# Sorties qui signalent un registre injoignable plutôt qu'une erreur des fichiers
NETWORK_ERRORS = re.compile(r"no such host|dial tcp|Forbidden|connection refused|timeout|could not connect|"
                            r"failed to request discovery document|i/o timeout|TLS handshake", re.I)


@dataclass
class CheckResult:
    id: str
    label: str
    status: str
    files: list[str] = field(default_factory=list)
    output: str = ""
    hint: str = ""
    seconds: float = 0.0

    @property
    def failed(self) -> bool:
        return self.status == FAILED


class Runner:
    """Exécute les commandes dans le dossier où les fichiers ont été écrits."""

    def __init__(self, root: Path):
        self.root = root

    def run(self, args: list[str], cwd: Path | None = None, stdin: str | None = None,
            timeout: int = TIMEOUT, env: dict[str, str] | None = None) -> tuple[int, str]:
        try:
            r = subprocess.run(args, cwd=cwd or self.root, input=stdin, capture_output=True, text=True,
                               timeout=timeout, env={**os.environ, **(env or {})})
        except subprocess.TimeoutExpired:
            return 124, f"Délai dépassé ({timeout} s) : {' '.join(args)}"
        return r.returncode, (r.stdout + r.stderr).strip()


@dataclass
class Check:
    id: str
    label: str
    select: Callable[[dict[str, str]], list[str]]
    # (runner, fichiers, commande de base) → (réussi, sortie) ; réussi = None : sauté (réseau indisponible)
    run: Callable[[Runner, list[str], list[str]], tuple[bool | None, str]]
    tools: tuple[str, ...] = ()       # un des exécutables suffit ; vide = Python seul
    hint: str = ""
    network: bool = False

    def command(self) -> list[str] | None:
        """Commande de base de l'outil, ou None s'il manque."""
        if not self.tools:
            return []
        for tool in self.tools:
            if tool == "check-jsonschema" and not shutil.which(tool):
                if importlib.util.find_spec("check_jsonschema"):
                    return [sys.executable, "-m", "check_jsonschema"]
                continue
            if tool.startswith("docker compose"):
                if shutil.which("docker") and subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0:
                    return ["docker", "compose"]
                continue
            if path := shutil.which(tool):
                return [path]
        return None


# --------------------------------------------------------------- sélections
def _yaml_files(files: dict[str, str]) -> list[str]:
    return sorted(f for f in files if f.endswith((".yml", ".yaml", ".json")) and "/templates/" not in f)


def _shell(files: dict[str, str]) -> list[str]:
    return sorted(f for f in files if f.endswith(".sh"))


def _workflows(files: dict[str, str]) -> list[str]:
    return sorted(f for f in files if f.startswith((".github/workflows/", ".gitea/workflows/")))


def _k8s_manifests(files: dict[str, str]) -> list[str]:
    """Manifestes Kubernetes écrits tels quels (hors chart Helm et fichiers Kustomization)."""
    out = []
    for rel, content in files.items():
        if not rel.endswith((".yml", ".yaml")) or "/templates/" in rel or rel.startswith("charts/"):
            continue
        try:
            docs = [d for d in yaml.safe_load_all(content) if isinstance(d, dict)]
        except yaml.YAMLError:
            continue
        if docs and all("apiVersion" in d and "kind" in d for d in docs) \
                and not any(d["kind"] == "Kustomization" and "kustomize.config" in str(d["apiVersion"]) for d in docs):
            out.append(rel)
    return sorted(out)


def _overlays(files: dict[str, str]) -> list[str]:
    return sorted(str(Path(f).parent) for f in files
                  if f.startswith("deploy/kustomize/overlays/") and f.endswith("kustomization.yaml"))


def _charts(files: dict[str, str]) -> list[str]:
    return sorted(str(Path(f).parent) for f in files if re.fullmatch(r"charts/[^/]+/Chart\.yaml", f))


def _terraform(files: dict[str, str]) -> list[str]:
    return sorted({str(Path(f).parent) for f in files if f.endswith(".tf")})


def _compose(files: dict[str, str]) -> list[str]:
    return sorted(f for f in files if Path(f).name in ("docker-compose.yml", "compose.yaml"))


def _playbooks(files: dict[str, str]) -> list[str]:
    return sorted(f for f in files if f.startswith("ansible/") and f.endswith((".yml", ".yaml")))


# --------------------------------------------------------------- exécutions
def _run_syntax(r: Runner, selected: list[str], _cmd: list[str]) -> tuple[bool, str]:
    errors = []
    for rel in selected:
        text = (r.root / rel).read_text(encoding="utf-8")
        try:
            if rel.endswith(".json"):
                json.loads(text)
            else:
                list(yaml.safe_load_all(text))
        except (yaml.YAMLError, json.JSONDecodeError) as exc:
            errors.append(f"{rel} : {exc}")
    return not errors, "\n".join(errors) or f"{len(selected)} fichier(s) lus sans erreur."


def _per_file(build: Callable[[list[str], str], list[str] | None]):
    """Lance la commande fichier par fichier ; build() renvoie None pour sauter un fichier."""
    def run(r: Runner, selected: list[str], cmd: list[str]) -> tuple[bool, str]:
        ok, lines = True, []
        for rel in selected:
            args = build(cmd, rel)
            if args is None:
                continue
            code, out = r.run(args)
            if code != 0:
                ok = False
                lines.append(f"✗ {rel}\n{out}")
            else:
                lines.append(f"✓ {rel}" + (f"\n{out}" if out else ""))
        return ok, "\n".join(lines)
    return run


def _schema_args(cmd: list[str], rel: str) -> list[str] | None:
    schema = SCHEMAS.get(rel)
    if schema is None:
        return None
    return [*cmd, "--regex-variant", "python", "--builtin-schema", schema, rel]


def _kubeconform_args(base: list[str]) -> list[str]:
    cache = Path.home() / ".cache" / "devops-builder" / "kubeconform"
    cache.mkdir(parents=True, exist_ok=True)
    return [*base, "-strict", "-summary", "-ignore-missing-schemas", "-cache", str(cache),
            "-schema-location", "default", "-schema-location", CRD_CATALOG]


def _run_kubeconform(r: Runner, selected: list[str], cmd: list[str]) -> tuple[bool | None, str]:
    code, out = r.run([*_kubeconform_args(cmd), *selected])
    if code != 0 and "could not find schema" not in out and NETWORK_ERRORS.search(out):
        return None, f"Schémas Kubernetes injoignables depuis ce poste :\n{out}"
    return code == 0, out


def _kubeconform_stdin(r: Runner, manifest: str, label: str) -> tuple[bool, str]:
    """Valide un rendu (Kustomize, Helm) si kubeconform est installé."""
    kc = shutil.which("kubeconform")
    if not kc:
        return True, f"{label} : rendu correct (kubeconform absent, schémas non vérifiés)."
    code, out = r.run([*_kubeconform_args([kc]), "-"], stdin=manifest)
    return code == 0, f"{label} : {out}"


def _run_kustomize(r: Runner, selected: list[str], cmd: list[str]) -> tuple[bool, str]:
    ok, lines = True, []
    for overlay in selected:
        args = [*cmd, "kustomize", overlay] if Path(cmd[0]).name == "kubectl" else [*cmd, "build", overlay]
        code, out = r.run(args)
        if code != 0:
            ok = False
            lines.append(f"✗ {overlay}\n{out}")
            continue
        good, msg = _kubeconform_stdin(r, out, overlay)
        ok &= good
        lines.append(("✓ " if good else "✗ ") + msg)
    return ok, "\n".join(lines)


def _run_helm(r: Runner, selected: list[str], cmd: list[str]) -> tuple[bool, str]:
    ok, lines = True, []
    for chart in selected:
        values = sorted(p.name for p in (r.root / chart).glob("values-*.yaml"))
        variants = [[]] + [["-f", f"{chart}/values.yaml", "-f", f"{chart}/{v}"] for v in values]
        code, out = r.run([*cmd, "lint", chart])
        ok &= code == 0
        lines.append(("✓ " if code == 0 else "✗ ") + f"helm lint {chart}\n{out}")
        for extra in variants:
            code, out = r.run([*cmd, "template", "test", chart, *extra])
            label = f"helm template {chart} {' '.join(extra[3:4]) or '(valeurs par défaut)'}"
            if code != 0:
                ok = False
                lines.append(f"✗ {label}\n{out}")
                continue
            good, msg = _kubeconform_stdin(r, out, label)
            ok &= good
            lines.append(("✓ " if good else "✗ ") + msg)
    return ok, "\n".join(lines)


def _run_tf_fmt(r: Runner, selected: list[str], cmd: list[str]) -> tuple[bool, str]:
    ok, lines = True, []
    for d in selected:
        code, out = r.run([*cmd, "fmt", "-check", "-diff", "-recursive", "-no-color"], cwd=r.root / d)
        ok &= code == 0
        lines.append(("✓ " if code == 0 else "✗ ") + d + (f"\n{out}" if out else ""))
    return ok, "\n".join(lines)


def _run_tf_validate(r: Runner, selected: list[str], cmd: list[str]) -> tuple[bool | None, str]:
    ok, lines = True, []
    for d in selected:
        cwd = r.root / d
        code, out = r.run([*cmd, "init", "-backend=false", "-input=false", "-no-color"], cwd=cwd, timeout=600)
        if code != 0 and NETWORK_ERRORS.search(out):
            return None, f"Registre de modules ou de providers injoignable depuis ce poste :\n{out}"
        if code != 0:
            ok = False
            lines.append(f"✗ {d} : init\n{out}")
            continue
        code, out = r.run([*cmd, "validate", "-no-color"], cwd=cwd)
        ok &= code == 0
        lines.append(("✓ " if code == 0 else "✗ ") + f"{d}\n{out}")
    return ok, "\n".join(lines)


def _run_ansible(r: Runner, selected: list[str], cmd: list[str]) -> tuple[bool, str]:
    playbooks = [p for p in selected if Path(p).name in ("site.yml", "deploy.yml")]
    inventory = next((f"ansible/{p}" for p in ("inventory.ini",) if (r.root / "ansible" / p).exists()), None)
    if inventory is None:
        inv = sorted((r.root / "ansible" / "inventories").glob("*.ini"))
        inventory = str(inv[0].relative_to(r.root)) if inv else None
    ok, lines = True, []
    for pb in playbooks:
        args = [*cmd, "--syntax-check", pb] + (["-i", inventory] if inventory else [])
        code, out = r.run(args)
        ok &= code == 0
        lines.append(("✓ " if code == 0 else "✗ ") + pb + (f"\n{out}" if out else ""))
    return ok, "\n".join(lines)


CHECKS: list[Check] = [
    Check("syntax", "Syntaxe YAML et JSON", _yaml_files, _run_syntax),
    Check("bash", "Syntaxe des scripts shell (bash -n)", _shell,
          _per_file(lambda cmd, rel: [*cmd, "-n", rel]), ("bash",), "bash est fourni par le système (Git Bash ou WSL sous Windows)."),
    Check("schemas", "Schémas officiels (CI, Compose, Renovate, Dependabot)",
          lambda f: sorted(x for x in f if x in SCHEMAS), _per_file(_schema_args), ("check-jsonschema",),
          "pip install check-jsonschema"),
    Check("actionlint", "Workflows GitHub et Gitea (actionlint)", _workflows,
          _per_file(lambda cmd, rel: [*cmd, "-shellcheck=", rel]), ("actionlint",),
          "pip install actionlint-py, ou https://github.com/rhysd/actionlint"),
    Check("shellcheck", "Scripts shell (ShellCheck)", _shell,
          _per_file(lambda cmd, rel: [*cmd, "-S", "warning", rel]), ("shellcheck",), "pip install shellcheck-py"),
    Check("compose", "Docker Compose (docker compose config)", _compose,
          _per_file(lambda cmd, rel: [*cmd, "-f", rel, "config", "-q"]), ("docker compose",),
          "Docker Desktop ou le plugin docker-compose"),
    Check("kubeconform", "Manifestes Kubernetes (kubeconform)", _k8s_manifests, _run_kubeconform, ("kubeconform",),
          "https://github.com/yannh/kubeconform/releases", network=True),
    Check("kustomize", "Rendu Kustomize par environnement", _overlays, _run_kustomize, ("kubectl", "kustomize"),
          "kubectl (https://kubernetes.io/docs/tasks/tools/) ou kustomize"),
    Check("helm", "Chart Helm (lint et rendu par environnement)", _charts, _run_helm, ("helm",),
          "https://helm.sh/docs/intro/install/"),
    Check("tf-fmt", "Terraform / OpenTofu : format", _terraform, _run_tf_fmt, ("tofu", "terraform"),
          "https://opentofu.org/docs/intro/install/"),
    Check("tf-validate", "Terraform / OpenTofu : init et validate", _terraform, _run_tf_validate,
          ("tofu", "terraform"), "https://opentofu.org/docs/intro/install/", network=True),
    Check("ansible", "Playbooks Ansible (--syntax-check)", _playbooks, _run_ansible, ("ansible-playbook",),
          "pip install ansible-core"),
]


def plan_checks(files: dict[str, str]) -> list[tuple[Check, list[str]]]:
    """Contrôles qui s'appliquent à ces fichiers, avec les fichiers concernés."""
    return [(c, sel) for c in CHECKS if (sel := c.select(files))]


def validate_files(files: dict[str, str], network: bool = True, only: set[str] | None = None,
                   on_result: Callable[[CheckResult], None] | None = None,
                   should_stop: Callable[[], bool] | None = None) -> list[CheckResult]:
    results: list[CheckResult] = []
    with tempfile.TemporaryDirectory(prefix="devops-builder-") as tmp:
        root = Path(tmp)
        for rel, content in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        runner = Runner(root)
        for check, selected in plan_checks(files):
            if only is not None and check.id not in only:
                continue
            if should_stop and should_stop():
                break
            res = CheckResult(check.id, check.label, OK, selected, hint=check.hint)
            cmd = check.command()
            if cmd is None:
                res.status = MISSING
                res.output = f"Outil introuvable : {' ou '.join(check.tools)}. Installation : {check.hint}"
            elif check.network and not network:
                res.status = SKIPPED
                res.output = "Contrôle sauté : il télécharge des schémas ou des providers (mode hors ligne)."
            else:
                start = time.monotonic()
                try:
                    ok, out = check.run(runner, selected, cmd)
                except Exception as exc:  # un outil inattendu ne doit pas arrêter la validation
                    ok, out = False, f"Erreur interne du contrôle : {exc}"
                res.seconds = time.monotonic() - start
                res.status = SKIPPED if ok is None else OK if ok else FAILED
                res.output = out.replace(str(root) + os.sep, "")
            results.append(res)
            if on_result:
                on_result(res)
    return results


def summary(results: list[CheckResult]) -> str:
    counts = {s: sum(1 for r in results if r.status == s) for s in (OK, FAILED, MISSING, SKIPPED)}
    parts = [f"{counts[OK]} réussi(s)", f"{counts[FAILED]} en échec"]
    if counts[MISSING]:
        parts.append(f"{counts[MISSING]} sans outil installé")
    if counts[SKIPPED]:
        parts.append(f"{counts[SKIPPED]} sauté(s)")
    return ", ".join(parts)
