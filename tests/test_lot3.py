# SPDX-License-Identifier: Apache-2.0
"""Lot 3 : validation locale, test kind, écriture prudente, export Git, variables CI.

Les outils externes (kind, kubectl, helm, docker, gh, glab) sont remplacés par de petits
scripts qui consignent leurs appels : on vérifie l'enchaînement, pas les outils eux-mêmes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from test_generators import MATRIX  # noqa: E402

from devops_builder import gitexport, sync  # noqa: E402
from devops_builder.catalog import default_catalog  # noqa: E402
from devops_builder.cli import main as cli  # noqa: E402
from devops_builder.generators import generate  # noqa: E402
from devops_builder.generators.civars import CI_VARIABLES  # noqa: E402
from devops_builder.generators.localtest import KIND_TEST  # noqa: E402
from devops_builder.model import Project  # noqa: E402
from devops_builder.validate import FAILED, MISSING, OK, SKIPPED, validate_files  # noqa: E402

CATALOG = default_catalog()
EXAMPLES = Path(__file__).parents[1] / "devops_builder" / "data" / "examples"
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git absent")


def files_of(name: str) -> dict[str, str]:
    return generate(MATRIX[name], CATALOG).files


def stub(bin_dir: Path, name: str, body: str) -> None:
    """Exécutable factice : consigne ses arguments dans $STUB_LOG puis exécute `body`."""
    path = bin_dir / name
    path.write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> "$STUB_LOG"\n{body}\n')
    path.chmod(0o755)


# ------------------------------------------------------------------ validation
def test_validation_signale_une_erreur_de_syntaxe():
    files = files_of("gitlab-compose")
    files[".gitlab-ci.yml"] = "stages: [build\n"
    results = {r.id: r for r in validate_files(files, network=False, only={"syntax"})}
    assert results["syntax"].status == FAILED
    assert ".gitlab-ci.yml" in results["syntax"].output


def test_validation_outil_absent_et_hors_ligne(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    files = files_of("jenkins-kustomize")
    results = {r.id: r for r in validate_files(files, network=False)}
    assert results["syntax"].status == OK                 # contrôle en Python : toujours disponible
    assert results["kustomize"].status == MISSING
    assert "kubectl" in results["kustomize"].output
    assert results["kubeconform"].status in (MISSING, SKIPPED)


@pytest.mark.skipif(shutil.which("check-jsonschema") is None, reason="check-jsonschema absent")
def test_validation_schema_refuse_une_ci_invalide():
    files = files_of("gitlab-compose")
    doc = yaml.safe_load(files[".gitlab-ci.yml"])
    doc["build-image"] = {"script": "echo", "when": "parfois"}
    files[".gitlab-ci.yml"] = yaml.safe_dump(doc)
    (res,) = validate_files(files, only={"schemas"})
    assert res.status == FAILED and ".gitlab-ci.yml" in res.output


@pytest.mark.parametrize("name", ["env-gitlab-eks", "env-github-argo", "env-jenkins-kustomize", "gitea-ansible",
                                  "env-woodpecker-flux"])
def test_les_fichiers_generes_passent_la_validation(name):
    results = validate_files(files_of(name), network=False)
    failed = [(r.label, r.output) for r in results if r.status == FAILED]
    assert failed == []


def test_validation_helm_avec_helm_factice(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub(bin_dir, "helm", 'if [ "$1" = template ]; then printf "apiVersion: v1\\nkind: Service\\nmetadata:\\n  name: x\\n"; fi')
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log"))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    (res,) = validate_files(files_of("env-gitlab-eks"), network=False, only={"helm"})
    assert res.status == OK, res.output
    calls = (tmp_path / "log").read_text()
    assert "helm lint charts/mon-app" in calls
    assert "values-production.yaml" in calls and "values-dev.yaml" in calls


def test_terraform_injoignable_est_saute_pas_en_echec(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub(bin_dir, "tofu", 'if [ "$1" = init ]; then echo "Failed to request discovery document: Forbidden" >&2; exit 1; fi')
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log"))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    (res,) = validate_files(files_of("env-gitlab-eks"), only={"tf-validate"})
    assert res.status == SKIPPED and "injoignable" in res.output


def test_cli_validate(capsys):
    code = cli(["validate", str(EXAMPLES / "01-web-hote-docker.devops.yaml"), "--offline"])
    out = capsys.readouterr().out
    assert code == 0 and "réussi" in out, out


# ------------------------------------------------------------------ écriture prudente
def test_plan_distingue_les_fichiers_retouches(tmp_path):
    files = files_of("gitlab-compose")
    first = sync.plan(files, tmp_path)
    assert {c.status for c in first} == {sync.NEW} and all(c.selected for c in first)
    sync.apply(first, tmp_path)
    assert json.loads((tmp_path / sync.MANIFEST).read_text())["files"].keys() == files.keys()

    (tmp_path / "PIPELINE.md").write_text("notes à moi\n")            # retouche manuelle
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")           # fichier du dépôt, ignoré
    files2 = dict(files)
    files2[".gitlab-ci.yml"] += "# changement du générateur\n"
    files2["renovate.json"] = files.get("renovate.json", "{}")
    del files2["deploy/docker-compose.yml"]
    by = {c.path: c for c in sync.plan(files2, tmp_path)}
    assert by[".gitlab-ci.yml"].status == sync.UPDATED and by[".gitlab-ci.yml"].selected
    assert by["PIPELINE.md"].status == sync.EDITED and not by["PIPELINE.md"].selected
    assert by["deploy/docker-compose.yml"].status == sync.OBSOLETE and not by["deploy/docker-compose.yml"].selected
    assert "Dockerfile" not in by
    assert by[".gitlab-ci.yml"].stats() == (1, 0)

    sync.apply(list(by.values()), tmp_path)
    assert (tmp_path / "PIPELINE.md").read_text() == "notes à moi\n"   # conservé
    again = {c.path: c for c in sync.plan(files2, tmp_path)}
    assert again["PIPELINE.md"].status == sync.EDITED                  # toujours signalé


def test_fichier_etranger_non_ecrase(tmp_path):
    files = files_of("gitlab-compose")
    (tmp_path / ".gitlab-ci.yml").write_text("stages: [test]\n")
    by = {c.path: c for c in sync.plan(files, tmp_path)}
    assert by[".gitlab-ci.yml"].status == sync.FOREIGN and not by[".gitlab-ci.yml"].selected
    assert "-stages: [test]" in by[".gitlab-ci.yml"].diff()


def test_cli_generate_sur_par_defaut(tmp_path, capsys):
    ex = str(EXAMPLES / "02-api-k3s-gitops.devops.yaml")
    assert cli(["generate", ex, "-o", str(tmp_path)]) == 0
    target = tmp_path / "PIPELINE.md"
    target.write_text("à moi\n")
    assert cli(["generate", ex, "-o", str(tmp_path)]) == 0
    assert target.read_text() == "à moi\n"
    assert "--overwrite" in capsys.readouterr().out
    assert cli(["generate", ex, "-o", str(tmp_path), "--overwrite"]) == 0
    assert target.read_text() != "à moi\n"


# ------------------------------------------------------------------ export Git
@pytest.mark.parametrize("url,forge,expected", [
    ("git@gitlab.com:groupe/sous/app.git", None,
     "https://gitlab.com/groupe/sous/app/-/merge_requests/new?merge_request%5Bsource_branch%5D=devops-builder%2Fx"
     "&merge_request%5Btarget_branch%5D=main"),
    ("https://github.com/izinum/app.git", None, "https://github.com/izinum/app/compare/main...devops-builder/x?expand=1"),
    ("ssh://git@git.exemple.fr:2222/equipe/app.git", "gitea", "https://git.exemple.fr/equipe/app/compare/main...devops-builder/x"),
    ("https://jeton@git.exemple.fr/equipe/app.git", "gitea", "https://git.exemple.fr/equipe/app/compare/main...devops-builder/x"),
    ("git@bitbucket.org:equipe/app.git", None,
     "https://bitbucket.org/equipe/app/pull-requests/new?source=devops-builder%2Fx&dest=main"),
    ("git@ssh.dev.azure.com:v3/org/projet/app", None,
     "https://dev.azure.com/org/projet/_git/app/pullrequestcreate?sourceRef=devops-builder%2Fx&targetRef=main"),
    ("https://org@dev.azure.com/org/projet/_git/app", None,
     "https://dev.azure.com/org/projet/_git/app/pullrequestcreate?sourceRef=devops-builder%2Fx&targetRef=main"),
    ("/srv/git/app.git", "gitlab", None),
])
def test_lien_de_demande_de_fusion(url, forge, expected):
    remote = gitexport.parse_remote(url)
    assert gitexport.request_url(gitexport.forge_of(remote, forge), remote, "devops-builder/x", "main") == expected


def _repo(tmp_path: Path, push_options: bool = False) -> tuple[Path, Path]:
    bare, work = tmp_path / "distant.git", tmp_path / "app"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    if push_options:
        subprocess.run(["git", "-C", str(bare), "config", "receive.advertisePushOptions", "true"], check=True)
        hook = bare / "hooks" / "post-receive"
        hook.write_text('#!/bin/sh\ni=0\nwhile [ $i -lt "${GIT_PUSH_OPTION_COUNT:-0}" ]; do\n'
                        '  eval "echo option: \\$GIT_PUSH_OPTION_$i"; i=$((i+1))\ndone\n'
                        'echo "View merge request for x:"\necho "  https://gitlab.exemple.fr/g/app/-/merge_requests/12"\n')
        hook.chmod(0o755)
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True, capture_output=True)
    for k, v in (("user.name", "Test"), ("user.email", "test@exemple.fr"), ("commit.gpgsign", "false"),
                 ("push.negotiate", "false")):
        subprocess.run(["git", "-C", str(work), "config", k, v], check=True)
    (work / "app.py").write_text("print('ok')\n")
    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "init"], check=True)
    subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "main"], check=True, capture_output=True)
    return bare, work


def _opts(**kw) -> gitexport.ExportOptions:
    base = dict(branch="devops-builder/essai", message="Pipeline", title="Pipeline DevOps Builder")
    return gitexport.ExportOptions(**{**base, **kw})


@needs_git
def test_export_git_branche_commit_push(tmp_path):
    bare, work = _repo(tmp_path)
    files = files_of("gitea-ansible")
    changes = sync.plan(files, work)
    out = gitexport.export(changes, work, _opts(forge="gitea"))
    assert out.pushed and out.commit
    assert gitexport.inspect(work).branch == "main"               # copie de travail revenue sur main
    assert not (work / ".gitea").exists()
    listing = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "devops-builder/essai"],
                             capture_output=True, text=True, check=True).stdout.split()
    assert ".gitea/workflows/pipeline.yml" in listing and "app.py" in listing and sync.MANIFEST in listing
    assert out.request_url is None and any("non reconnu" in m for m in out.messages)  # distant local


@needs_git
def test_export_git_gitlab_cree_la_merge_request(tmp_path):
    bare, work = _repo(tmp_path, push_options=True)
    out = gitexport.export(sync.plan(files_of("gitlab-compose"), work), work, _opts(forge="gitlab"))
    assert out.request_created and out.request_url.endswith("/merge_requests/12")


@needs_git
def test_export_git_refuse_une_copie_modifiee(tmp_path):
    _, work = _repo(tmp_path)
    (work / "app.py").write_text("print('modifié')\n")
    with pytest.raises(gitexport.GitError, match="non commitées"):
        gitexport.export(sync.plan(files_of("gitlab-compose"), work), work, _opts())
    assert gitexport.inspect(work).branch == "main"


@needs_git
def test_export_git_push_en_echec_garde_le_commit(tmp_path):
    bare, work = _repo(tmp_path)
    subprocess.run(["git", "-C", str(work), "remote", "set-url", "origin", str(tmp_path / "absent.git")], check=True)
    with pytest.raises(gitexport.GitError, match="push a échoué"):
        gitexport.export(sync.plan(files_of("gitlab-compose"), work), work, _opts())
    info = gitexport.inspect(work)
    assert info.branch == "main" and not info.dirty and not (work / ".gitlab-ci.yml").exists()
    branches = subprocess.run(["git", "-C", str(work), "branch"], capture_output=True, text=True).stdout
    assert "devops-builder/essai" in branches


@needs_git
def test_export_git_depot_vide(tmp_path):
    work = tmp_path / "vide"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    for k, v in (("user.name", "Test"), ("user.email", "t@e.fr"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(work), "config", k, v], check=True)
    out = gitexport.export(sync.plan(files_of("gitlab-compose"), work), work, _opts())
    assert out.branch == "main" and out.commit and (work / ".gitlab-ci.yml").exists()


@needs_git
def test_cli_export_git(tmp_path, capsys):
    bare, work = _repo(tmp_path)
    code = cli(["export-git", str(EXAMPLES / "01-web-hote-docker.devops.yaml"), "--repo", str(work),
                "--branch", "devops-builder/cli"])
    assert code == 0, capsys.readouterr().out
    assert "devops-builder/cli" in subprocess.run(["git", "-C", str(bare), "branch"], capture_output=True,
                                                  text=True).stdout


# ------------------------------------------------------------------ test kind
def _kind_stubs(tmp_path: Path, curl_code: str = "200") -> tuple[Path, Path]:
    bin_dir, log = tmp_path / "bin", tmp_path / "appels.log"
    bin_dir.mkdir()
    stub(bin_dir, "kind", "exit 0")                       # aucun cluster existant
    stub(bin_dir, "docker", "exit 0")
    stub(bin_dir, "helm", "exit 0")
    stub(bin_dir, "kustomize", 'echo "kind: Deployment"')
    stub(bin_dir, "kubectl", 'case "$*" in *port-forward*) exec sleep 5 ;; *jsonpath*) echo "0 0" ;; '
                             '*"-o yaml"*) echo "kind: Namespace" ;; *"-f -"*) cat >/dev/null ;; esac; exit 0')
    stub(bin_dir, "curl", f'echo -n {curl_code}')
    return bin_dir, log


def _run_kind(files: dict[str, str], tmp_path: Path, bin_dir: Path, log: Path, *args: str,
              **env: str) -> subprocess.CompletedProcess:
    root = tmp_path / "depot"
    for rel, content in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content)
    return subprocess.run(["bash", str(root / KIND_TEST), *args], capture_output=True, text=True, timeout=60,
                          stdin=subprocess.DEVNULL,
                          env={**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin", "STUB_LOG": str(log), **env})


def test_kind_helm_construit_charge_et_deploie(tmp_path):
    bin_dir, log = _kind_stubs(tmp_path)
    app = tmp_path / "code"
    app.mkdir()
    (app / "Dockerfile").write_text("FROM scratch\n")
    r = _run_kind(files_of("env-gitlab-eks"), tmp_path, bin_dir, log, "staging", APP_DIR=str(app))
    assert r.returncode == 0, r.stdout + r.stderr
    calls = log.read_text().splitlines()
    order = [next(i for i, c in enumerate(calls) if c.startswith(p)) for p in
             ("kind create cluster", "docker build", "kind load docker-image", "helm --kube-context",
              "kubectl --context kind-mon-app-test -n mon-app-staging rollout status", "kind delete cluster")]
    assert order == sorted(order)
    helm = next(c for c in calls if c.startswith("helm --kube-context"))
    assert "values-staging.yaml" in helm and "image.repository=devops-builder.local/mon-app" in helm
    assert "Test réussi" in r.stdout


def test_kind_kustomize_sans_code_fait_un_dry_run(tmp_path):
    bin_dir, log = _kind_stubs(tmp_path)
    r = _run_kind(files_of("env-jenkins-kustomize"), tmp_path, bin_dir, log, APP_DIR=str(tmp_path / "rien"))
    assert r.returncode == 0, r.stdout + r.stderr
    calls = log.read_text()
    assert "kustomize build" in calls and "--dry-run=server" in calls
    assert "docker build" not in calls and "rollout status" not in calls
    assert "kind delete cluster" in calls


def test_kind_echec_si_l_application_ne_repond_pas(tmp_path):
    bin_dir, log = _kind_stubs(tmp_path, curl_code="000")
    stub(bin_dir, "sleep", "exit 0")
    r = _run_kind(files_of("env-gitlab-eks"), tmp_path, bin_dir, log, IMAGE="registre/app:1")
    assert r.returncode == 1 and "ne répond pas" in r.stderr
    assert "kind delete cluster" in log.read_text()        # nettoyage même en cas d'échec


def test_kind_environnement_inconnu(tmp_path):
    bin_dir, log = _kind_stubs(tmp_path)
    r = _run_kind(files_of("env-gitlab-eks"), tmp_path, bin_dir, log, "recette")
    assert r.returncode == 2 and "dev, staging, production" in r.stderr


def test_pas_de_test_kind_sans_kubernetes():
    assert KIND_TEST not in files_of("gitlab-compose")


# ------------------------------------------------------------------ variables CI
def _ci_vars(files: dict[str, str], tmp_path: Path, bin_dir: Path, env: dict[str, str],
             *args: str) -> subprocess.CompletedProcess:
    script = tmp_path / "ci-variables.sh"
    script.write_text(files[CI_VARIABLES])
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
                          cwd=tmp_path, env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", **env})


def test_variables_github_secrets_et_vars(tmp_path):
    files = generate(MATRIX["github-static-gke"], CATALOG).files
    bin_dir, log = tmp_path / "bin", tmp_path / "log"
    bin_dir.mkdir()
    stub(bin_dir, "gh", 'cat > "$STUB_LOG.stdin.$3"')
    key = tmp_path / "cle.json"
    key.write_text('{"type": "service_account"}\n')
    r = _ci_vars(files, tmp_path, bin_dir, {"STUB_LOG": str(log), "GCP_SA_KEY_FILE": str(key)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "gh secret set GCP_SA_KEY" in log.read_text()
    assert Path(f"{log}.stdin.GCP_SA_KEY").read_text() == '{"type": "service_account"}\n'  # saut de ligne gardé


def test_variables_gitlab_masque_si_possible(tmp_path):
    p = Project.load(EXAMPLES / "01-web-hote-docker.devops.yaml")
    files = generate(p, CATALOG).files
    bin_dir, log = tmp_path / "bin", tmp_path / "log"
    bin_dir.mkdir()
    stub(bin_dir, "glab", '[ "$2" = set ] && [ "$3" = SSH_PRIVATE_KEY ] && exit 1; cat >/dev/null')
    env = {"STUB_LOG": str(log), "SSH_PRIVATE_KEY": "-----BEGIN KEY-----\nabc\n-----END KEY-----",
           "REGISTRY_PASSWORD": "s3cr3tValeur", "REGISTRY_USER": "robot"}
    r = _ci_vars(files, tmp_path, bin_dir, env)
    calls = log.read_text()
    assert r.returncode == 0, r.stdout + r.stderr
    assert re.search(r"glab variable set REGISTRY_PASSWORD .*--masked", calls)
    assert not re.search(r"set REGISTRY_USER .*--masked", calls)        # trop court pour être masqué
    assert "glab variable update SSH_PRIVATE_KEY" in calls              # existait déjà
    assert "ne peut pas être masquée" in r.stderr


def test_variables_dry_run_n_envoie_rien(tmp_path):
    files = generate(MATRIX["github-static-gke"], CATALOG).files
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    r = _ci_vars(files, tmp_path, bin_dir, {"GCP_SA_KEY": "x" * 12, "PATH": f"{bin_dir}:/usr/bin:/bin"}, "--dry-run")
    assert r.returncode == 0 and "serait déclarée" in r.stdout and "rien n'a été envoyé" in r.stdout


class _Gitea(BaseHTTPRequestHandler):
    calls: list[tuple[str, str, dict, str]] = []
    existing = {"REGISTRY_USER"}

    def _handle(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        self.calls.append((self.command, self.path, body, self.headers.get("Authorization", "")))
        name = self.path.rsplit("/", 1)[-1]
        code = 409 if self.command == "POST" and name in self.existing else 201 if self.command == "POST" else 204
        self.send_response(code)
        self.end_headers()

    do_PUT = do_POST = _handle

    def log_message(self, *_):
        pass


@pytest.mark.skipif(shutil.which("jq") is None or shutil.which("curl") is None, reason="jq ou curl absent")
def test_variables_gitea_par_l_api(tmp_path):
    ir_files = generate(MATRIX["gitea-ansible"], CATALOG)
    for v in ir_files.ir.variables:
        if v.name == "REGISTRY_USER":
            v.secret = False  # variable non secrète déjà présente : POST 409 puis PUT
    from devops_builder.generators.civars import ci_variables
    files = ci_variables(ir_files.ir)
    server = HTTPServer(("127.0.0.1", 0), _Gitea)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = {"GITEA_URL": f"http://127.0.0.1:{server.server_port}", "GITEA_REPO": "equipe/app",
               "GITEA_TOKEN": "jeton", "REGISTRY_USER": "robot", "REGISTRY_PASSWORD": "mdp",
               "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}
        r = _ci_vars(files, tmp_path, tmp_path, env)
    finally:
        server.shutdown()
    assert r.returncode == 0, r.stdout + r.stderr
    calls = [(m, p, b) for m, p, b, auth in _Gitea.calls]
    assert ("PUT", "/api/v1/repos/equipe/app/actions/secrets/REGISTRY_PASSWORD",
            {"data": "mdp", "description": "Mot de passe ou jeton de publication sur registry.example.com"}) in calls
    assert [m for m, p, _ in calls if p.endswith("variables/REGISTRY_USER")] == ["POST", "PUT"]
    assert all(auth == "token jeton" for *_, auth in _Gitea.calls)


def test_pas_de_script_pour_une_ci_non_prise_en_charge():
    assert CI_VARIABLES not in files_of("jenkins-kustomize")


@pytest.mark.parametrize("name", [n for n in MATRIX if "github" in n])
def test_references_github_declarees(name):
    result = generate(MATRIX[name], CATALOG)
    wf = result.files.get(".github/workflows/pipeline.yml", "")
    refs = set(re.findall(r"\$\{\{\s*(?:secrets|vars)\.([A-Z0-9_]+)\s*\}\}", wf)) - {"GITHUB_TOKEN"}
    declared = {v.name for v in result.ir.variables}
    assert refs <= declared, refs - declared


def test_azure_pipelines_mappe_les_secrets():
    doc = yaml.safe_load(files_of("azure-aks")["azure-pipelines.yml"])
    steps = [s for st in doc["stages"] for j in st["jobs"]
             for s in (j.get("steps") or j["strategy"]["runOnce"]["deploy"]["steps"]) if "script" in s]
    assert steps and all(s["env"]["REGISTRY_PASSWORD"] == "$(REGISTRY_PASSWORD)" for s in steps)


def test_github_azure_statique_utilise_le_secret_declare():
    p = MATRIX["aks-monitor"].model_copy(deep=True)
    p.cloud_auth = "static"
    p.stages["build"] = [b for b in p.stages["build"] if b.tool != "azure-pipelines"]
    p.stages["source"] = []
    p.add("github", "source")
    p.add("github-actions", "build")
    result = generate(p, CATALOG)
    wf = result.files[".github/workflows/pipeline.yml"]
    assert "AZURE_CREDENTIALS" not in wf and "secrets.AZURE_CLIENT_SECRET" in wf


def test_outil_installe_dans_l_environnement_de_l_application(tmp_path, monkeypatch):
    """Installation par pipx : `pipx inject izinum-devops-builder shellcheck-py` met l'outil à côté de l'interpréteur,
    hors du PATH ; la validation doit le trouver quand même."""
    from devops_builder import validate

    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    tool = venv_bin / "shellcheck"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    monkeypatch.setattr(validate.sys, "executable", str(venv_bin / "python"))
    monkeypatch.setenv("PATH", str(tmp_path / "vide"))
    check = next(c for c in validate.CHECKS if c.id == "shellcheck")
    assert check.command() == [str(tool)]


def test_conseil_d_installation_sous_pipx(monkeypatch):
    from devops_builder import validate

    monkeypatch.setattr(validate.sys, "prefix", "/Users/v/.local/pipx/venvs/devops-builder")
    assert validate.install_hint("pip install shellcheck-py") == "pipx inject izinum-devops-builder shellcheck-py"
    assert validate.install_hint("https://opentofu.org/docs/intro/install/").startswith("https://")
    monkeypatch.setattr(validate.sys, "prefix", "/usr")
    assert validate.install_hint("pip install shellcheck-py") == "pip install shellcheck-py"


def test_collection_ansible_absente_donne_la_commande(tmp_path, monkeypatch):
    from devops_builder import validate as v
    (tmp_path / "ansible").mkdir()
    (tmp_path / "ansible/requirements.yml").write_text("collections: []\n")
    monkeypatch.setattr(v.Runner, "run", lambda self, args, **kw: (
        4, "[ERROR]: couldn't resolve module/action 'community.docker.docker_compose_v2'."))
    ok, out = v._run_ansible(v.Runner(tmp_path), ["ansible/deploy.yml"], ["ansible-playbook"])
    assert not ok
    assert out.endswith("ansible-galaxy collection install -r ansible/requirements.yml")
