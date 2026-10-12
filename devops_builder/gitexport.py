# SPDX-License-Identifier: Apache-2.0
"""Export des fichiers générés vers un dépôt Git : branche dédiée, commit, push, demande de fusion.

Rien n'est écrit sur la branche courante : les fichiers partent sur une nouvelle branche,
et la copie de travail revient ensuite sur la branche de départ. La demande de fusion est
créée directement quand la forge le permet sans jeton supplémentaire (options de push
GitLab, CLI gh déjà connectée) ; sinon, un lien de création pré-rempli est proposé.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from . import sync

FORGE_LABELS = {
    "gitlab": "merge request GitLab", "github": "pull request GitHub", "gitea": "pull request Gitea",
    "bitbucket": "pull request Bitbucket", "azure-devops": "pull request Azure DevOps",
}
KNOWN_HOSTS = {"github.com": "github", "gitlab.com": "gitlab", "bitbucket.org": "bitbucket",
               "dev.azure.com": "azure-devops", "ssh.dev.azure.com": "azure-devops", "codeberg.org": "gitea",
               "gitea.com": "gitea"}
BRANCH_PATTERN = re.compile(r"^(?!/)(?!.*//)(?!.*\.\.)(?!.*@\{)[A-Za-z0-9._/-]+(?<![./])$")


class GitError(RuntimeError):
    pass


# ------------------------------------------------------------------ remotes
@dataclass
class RemoteInfo:
    url: str
    host: str | None        # hôte web (sans port SSH)
    path: str               # chemin du dépôt, sans .git
    scheme: str = "https"

    @property
    def web(self) -> str | None:
        if not self.host:
            return None
        if self.host in ("dev.azure.com", "ssh.dev.azure.com"):
            return azure_web(self.path)
        return f"{self.scheme}://{self.host}/{self.path}"


def azure_web(path: str) -> str:
    """Azure DevOps : v3/org/projet/depot (SSH) ou org/projet/_git/depot (HTTPS)."""
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] == "v3":
        parts = parts[1:]
    if "_git" in parts:
        i = parts.index("_git")
        org_project, repo = parts[:i], parts[i + 1:]
    else:
        org_project, repo = parts[:-1], parts[-1:]
    return "https://dev.azure.com/" + "/".join(org_project + ["_git"] + repo)


def parse_remote(url: str) -> RemoteInfo:
    u = url.strip()
    m = re.match(r"^(?P<scheme>https?)://(?:[^@/]+@)?(?P<host>[^/]+)/(?P<path>.+?)(?:\.git)?/?$", u)
    if m:
        return RemoteInfo(u, m["host"], m["path"], m["scheme"])
    m = re.match(r"^ssh://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/(?P<path>.+?)(?:\.git)?/?$", u)
    if m:
        return RemoteInfo(u, m["host"], m["path"])
    m = re.match(r"^(?:[^@/]+@)?(?P<host>[A-Za-z0-9.-]+):(?!//)(?P<path>.+?)(?:\.git)?/?$", u)
    if m and not re.match(r"^[A-Za-z]:\\", u):
        return RemoteInfo(u, m["host"], m["path"].lstrip("/"))
    return RemoteInfo(u, None, u)


def forge_of(remote: RemoteInfo, project_forge: str | None) -> str | None:
    if remote.host:
        host = remote.host.split(":")[0].lower()
        if host in KNOWN_HOSTS:
            return KNOWN_HOSTS[host]
        if host.endswith(".visualstudio.com"):
            return "azure-devops"
    return project_forge


def request_url(forge: str | None, remote: RemoteInfo, branch: str, base: str) -> str | None:
    """Lien de création de la demande de fusion, pré-rempli avec les deux branches."""
    web = remote.web
    if not web or not forge:
        return None
    b, t = quote(branch, safe="/"), quote(base, safe="/")
    if forge == "gitlab":
        return (f"{web}/-/merge_requests/new?merge_request%5Bsource_branch%5D={quote(branch, safe='')}"
                f"&merge_request%5Btarget_branch%5D={quote(base, safe='')}")
    if forge == "github":
        return f"{web}/compare/{t}...{b}?expand=1"
    if forge == "gitea":
        return f"{web}/compare/{t}...{b}"
    if forge == "bitbucket":
        return f"{web}/pull-requests/new?source={quote(branch, safe='')}&dest={quote(base, safe='')}"
    if forge == "azure-devops":
        return f"{web}/pullrequestcreate?sourceRef={quote(branch, safe='')}&targetRef={quote(base, safe='')}"
    return None


# ------------------------------------------------------------------ dépôt
def _git(repo: Path, *args: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
    if not shutil.which("git"):
        raise GitError("Git n'est pas installé sur ce poste.")
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise GitError(f"git {' '.join(args)} a échoué :\n{(r.stderr or r.stdout).strip()}")
    return r


@dataclass
class RepoInfo:
    root: Path
    branch: str | None          # None : HEAD détachée
    has_commits: bool
    remotes: dict[str, str]
    dirty: list[str]            # fichiers suivis modifiés ou indexés

    @property
    def default_remote(self) -> str | None:
        return "origin" if "origin" in self.remotes else next(iter(self.remotes), None)


def inspect(path: str | Path) -> RepoInfo:
    path = Path(path)
    r = _git(path, "rev-parse", "--show-toplevel", check=False)
    if r.returncode != 0:
        raise GitError(f"{path} n'est pas un dépôt Git.")
    root = Path(r.stdout.strip())
    head = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = head.stdout.strip() if head.returncode == 0 else None
    has_commits = _git(root, "rev-parse", "--verify", "--quiet", "HEAD", check=False).returncode == 0
    remotes = {}
    for line in _git(root, "remote", "-v").stdout.splitlines():
        name, url, *_ = line.split()
        remotes.setdefault(name, url)
    dirty = [line[3:] for line in _git(root, "status", "--porcelain", "--untracked-files=no").stdout.splitlines()]
    return RepoInfo(root, branch, has_commits, remotes, dirty)


def default_branch_name(prefix: str = "devops-builder") -> str:
    return f"{prefix}/{datetime.now().strftime('%Y%m%d-%H%M')}"


@dataclass
class ExportOptions:
    branch: str
    message: str
    title: str
    description: str = ""
    push: bool = True
    remote: str | None = None
    open_request: bool = True
    forge: str | None = None          # forge du projet, utilisée si l'hôte n'est pas reconnu


@dataclass
class ExportOutcome:
    branch: str
    base: str
    commit: str | None = None
    files: list[str] = field(default_factory=list)
    pushed: bool = False
    request_url: str | None = None
    request_created: bool = False
    messages: list[str] = field(default_factory=list)


def export(changes: list[sync.FileChange], repo: str | Path, opts: ExportOptions,
           log: Callable[[str], None] | None = None) -> ExportOutcome:
    """Écrit les changements sélectionnés sur une nouvelle branche et la pousse."""
    say = log or (lambda _m: None)
    info = inspect(repo)
    root = info.root
    if info.dirty:
        raise GitError("La copie de travail a des modifications non commitées :\n  "
                       + "\n  ".join(info.dirty[:10]) + "\nLes committer ou les mettre de côté (git stash) avant l'export.")
    if info.branch is None and info.has_commits:
        raise GitError("HEAD est détachée : se placer sur une branche avant l'export.")
    if not BRANCH_PATTERN.match(opts.branch):
        raise GitError(f"Nom de branche invalide : « {opts.branch} ».")
    if _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{opts.branch}", check=False).returncode == 0:
        raise GitError(f"La branche « {opts.branch} » existe déjà.")
    base = info.branch or "main"
    out = ExportOutcome(opts.branch, base)
    selected = [c for c in changes if c.selected]
    if not selected:
        raise GitError("Aucun fichier sélectionné : rien à exporter.")

    first_commit = not info.has_commits
    if first_commit:
        # Dépôt vide : premier commit directement sur la branche courante, sans demande de fusion.
        out.branch = base
        out.messages.append(f"Dépôt sans commit : les fichiers forment le premier commit de « {base} ».")
    else:
        say(f"Création de la branche {opts.branch} depuis {base}")
        _git(root, "switch", "-c", opts.branch)
    try:
        out.files = sync.apply(changes, root)
        written = out.files
        _git(root, "add", "-A", "--", *written)
        staged = _git(root, "diff", "--cached", "--name-only").stdout.split()
        if not staged:
            raise GitError("Les fichiers sont déjà à jour sur cette branche : rien à committer.")
        say(f"Commit de {len(staged)} fichier(s)")
        r = _git(root, "commit", "-m", opts.message, check=False)
        if r.returncode != 0:
            err = (r.stderr or r.stdout).strip()
            if "user.email" in err or "Please tell me who you are" in err:
                err = "Identité Git absente : git config --global user.name « … » et user.email « … »."
            raise GitError(f"Commit impossible : {err}")
        out.commit = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
        remote_name = opts.remote or info.default_remote
        if opts.push and remote_name:
            _push(root, remote_name, info.remotes.get(remote_name, ""), out, opts, first_commit, say)
        elif opts.push:
            out.messages.append("Aucun dépôt distant configuré : la branche reste locale.")
    except Exception:
        if not first_commit:
            _git(root, "reset", "--hard", "--quiet", check=False)
            if out.files:
                _git(root, "clean", "-f", "--quiet", "--", *out.files, check=False)
            _git(root, "switch", "--quiet", base, check=False)
            if out.commit is None:
                _git(root, "branch", "-D", opts.branch, check=False)
        raise
    if not first_commit:
        _git(root, "switch", "--quiet", base)
        out.messages.append(f"La copie de travail est revenue sur « {base} » ; les fichiers sont sur « {opts.branch} ».")
    return out


def _push(root: Path, remote_name: str, remote_url: str, out: ExportOutcome, opts: ExportOptions,
          first_commit: bool, say: Callable[[str], None]) -> None:
    remote = parse_remote(remote_url)
    forge = forge_of(remote, opts.forge)
    options: list[str] = []
    gitlab_mr = opts.open_request and not first_commit and forge == "gitlab"
    if gitlab_mr:
        options += ["-o", "merge_request.create", "-o", f"merge_request.target={out.base}",
                 "-o", f"merge_request.title={opts.title}", "-o", "merge_request.remove_source_branch"]
        # une option de push ne peut pas contenir de saut de ligne
        options += ["-o", "merge_request.description=Généré par DevOps Builder ; voir PIPELINE.md pour les variables "
                       "CI à déclarer et les avertissements."]
    say(f"Envoi de {out.branch} vers {remote_name}")
    r = _git(root, "push", *options, "-u", remote_name, out.branch, check=False, timeout=300)
    text = (r.stdout + r.stderr).strip()
    if r.returncode != 0 and gitlab_mr and "push options" in text.lower():
        gitlab_mr = False  # serveur sans options de push : envoi simple, lien de création ensuite
        r = _git(root, "push", "-u", remote_name, out.branch, check=False, timeout=300)
        text = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        raise GitError(f"Le push a échoué ; le commit {out.commit} reste sur la branche locale « {out.branch} ».\n{text}")
    out.pushed = True
    if first_commit or not opts.open_request:
        return
    found = re.search(r"https?://\S+/-/merge_requests/\d+", text)
    if gitlab_mr and found:
        out.request_url, out.request_created = found.group(0), True
        return
    if forge == "github" and shutil.which("gh") and remote.host:
        say("Création de la pull request avec gh")
        gh = subprocess.run(["gh", "pr", "create", "--repo", f"{remote.host}/{remote.path}", "--base", out.base,
                             "--head", out.branch, "--title", opts.title, "--body", opts.description or opts.title],
                            cwd=root, capture_output=True, text=True, timeout=120)
        link = re.search(r"https?://\S+/pull/\d+", gh.stdout)
        if gh.returncode == 0 and link:
            out.request_url, out.request_created = link.group(0), True
            return
        out.messages.append("gh n'a pas pu créer la pull request (gh auth login ?) : lien de création proposé.")
    out.request_url = request_url(forge, remote, out.branch, out.base)
    if out.request_url is None:
        out.messages.append("Forge ou dépôt distant non reconnu : créer la demande de fusion depuis l'interface de la forge.")


def describe_changes(changes: list[sync.FileChange]) -> str:
    lines = [f"- `{c.path}` : {c.status}" for c in changes if c.selected]
    return "Fichiers générés par DevOps Builder :\n\n" + "\n".join(lines[:60]) + (
        "\n- …" if len(lines) > 60 else "") + "\n\nDétails, variables CI à déclarer et avertissements : PIPELINE.md."
