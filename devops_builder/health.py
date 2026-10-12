# SPDX-License-Identifier: Apache-2.0
"""Entretien du catalogue : ce qui a changé depuis la vérification des fiches.

Contrôles hors ligne : maturité dans le Landscape, fiche disparue du Landscape, date de
vérification ancienne, références vers des fiches inexistantes, capacités que personne ne
fournit, fiches personnelles invalides.

Contrôles en ligne (API GitHub et GitLab.com) : dépôt archivé, licence changée, dépôt
renommé ou introuvable, absence d'activité. Les réponses sont gardées en cache 24 h ; un
jeton (GITHUB_TOKEN, GH_TOKEN ou `gh auth token`) lève la limite de 60 requêtes par heure.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from . import userdata
from .catalog import Catalog
from .model import OSS_LICENSES, Tool

TO_FIX, WATCH, INFO = "à corriger", "à surveiller", "info"
LEVELS = (TO_FIX, WATCH, INFO)


def _github_api() -> str:
    return os.environ.get("DEVOPS_BUILDER_GITHUB_API", "https://api.github.com")


def _gitlab_api() -> str:
    return os.environ.get("DEVOPS_BUILDER_GITLAB_API", "https://gitlab.com/api/v4")


CACHE_TTL = 24 * 3600
STALE_DAYS = 180
INACTIVE_DAYS = 540
# Équivalences de licences : identifiant renvoyé par la forge → notation des fiches
LICENSE_ALIASES = {"BUSL-1.1": "BSL-1.1", "AGPL-3.0-ONLY": "AGPL-3.0", "AGPL-3.0-OR-LATER": "AGPL-3.0",
                   "GPL-3.0-ONLY": "GPL-3.0", "GPL-3.0-OR-LATER": "GPL-3.0", "LGPL-3.0-ONLY": "LGPL-3.0",
                   "LGPL-2.1-ONLY": "LGPL-2.1", "LGPL-2.1-OR-LATER": "LGPL-2.1", "GPL-2.0-ONLY": "GPL-2.0",
                   "LGPL-3.0-OR-LATER": "LGPL-3.0", "GPL-2.0-OR-LATER": "GPL-2.0"}
GITLAB_LICENSES = {"mit": "MIT", "apache-2.0": "Apache-2.0", "gpl-3.0": "GPL-3.0", "agpl-3.0": "AGPL-3.0",
                   "lgpl-3.0": "LGPL-3.0", "mpl-2.0": "MPL-2.0", "bsd-3-clause": "BSD-3-Clause",
                   "bsd-2-clause": "BSD-2-Clause", "gpl-2.0": "GPL-2.0", "lgpl-2.1": "LGPL-2.1"}
UNKNOWN_LICENSES = {None, "", "NOASSERTION", "OTHER", "other"}


def normalize_license(value: str | None) -> str | None:
    if value is None or value in UNKNOWN_LICENSES:
        return None
    up = value.upper()
    if up in LICENSE_ALIASES:
        return LICENSE_ALIASES[up]
    for known in (*OSS_LICENSES, "BSL-1.1", "SSPL-1.0", "Elastic-2.0"):
        if known.upper() == up:
            return known
    return value


@dataclass
class Finding:
    tool_id: str
    tool_name: str
    kind: str
    level: str
    message: str
    fix: dict | None = None
    fix_label: str = ""


@dataclass
class RepoStatus:
    url: str
    checked_at: float = 0.0
    found: bool = True
    archived: bool | None = None
    license: str | None = None
    pushed_at: str | None = None
    canonical: str | None = None        # URL après renommage ou transfert
    error: str | None = None            # erreur réseau ou limite d'API : rien de conclu

    @property
    def usable(self) -> bool:
        return self.error is None


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    checked: int = 0                    # fiches examinées
    repos_checked: int = 0
    repos_failed: list[str] = field(default_factory=list)
    network: bool = True

    def by_level(self, level: str) -> list[Finding]:
        return [f for f in self.findings if f.level == level]

    def summary(self) -> str:
        parts = [f"{self.checked} fiche(s) examinée(s)"]
        if self.network:
            parts.append(f"{self.repos_checked} dépôt(s) interrogé(s)")
        parts += [f"{len(self.by_level(lv))} {lv}" for lv in LEVELS]
        text = ", ".join(parts)
        if self.repos_failed:
            text += f" ; {len(self.repos_failed)} dépôt(s) non vérifié(s) (réseau ou limite d'API)"
        if not self.network:
            text += " ; dépôts non interrogés (hors ligne)"
        return text

    def markdown(self) -> str:
        out = [f"# Entretien du catalogue — {date.today().isoformat()}", "", self.summary() + ".", ""]
        for level in LEVELS:
            items = self.by_level(level)
            if not items:
                continue
            out += [f"## {level.capitalize()} ({len(items)})", ""]
            for f in items:
                fix = f" — correction proposée : {f.fix_label}" if f.fix else ""
                out.append(f"- **{f.tool_name}** (`{f.tool_id}`) : {f.message}{fix}")
            out.append("")
        if self.repos_failed:
            out += ["## Dépôts non vérifiés", ""] + [f"- {u}" for u in self.repos_failed] + [""]
        return "\n".join(out)


# ----------------------------------------------------------------- dépôts
def parse_repo(url: str) -> tuple[str, str] | None:
    """(forge, chemin) pour github.com et gitlab.com ; None si la forge n'est pas interrogeable."""
    m = re.match(r"^https?://(?:www\.)?(github\.com|gitlab\.com)/([^?#]+?)(?:\.git)?/?$", url.strip())
    if not m:
        return None
    path = m[2]
    if m[1] == "github.com":
        parts = path.split("/")
        if len(parts) < 2:
            return None
        return "github", "/".join(parts[:2])
    return "gitlab", path


def github_token() -> str | None:
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    if shutil.which("gh"):
        try:
            r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def _get_json(url: str, token: str | None = None, timeout: int = 20) -> tuple[int, dict]:
    headers = {"User-Agent": "devops-builder", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8") or "{}")
        except ValueError:
            body = {}
        return exc.code, body


def fetch_repo(url: str, token: str | None = None) -> RepoStatus:
    parsed = parse_repo(url)
    status = RepoStatus(url=url, checked_at=time.time())
    if parsed is None:
        status.error = "forge non interrogeable"
        return status
    forge, path = parsed
    try:
        if forge == "github":
            code, data = _get_json(f"{_github_api()}/repos/{path}", token)
            if code == 404:
                status.found = False
            elif code != 200:
                status.error = f"HTTP {code} {data.get('message', '')}".strip()
            else:
                status.archived = bool(data.get("archived") or data.get("disabled"))
                status.license = (data.get("license") or {}).get("spdx_id")
                status.pushed_at = data.get("pushed_at")
                full = data.get("full_name")
                if full and full.lower() != path.lower():
                    status.canonical = f"https://github.com/{full}"
        else:
            code, data = _get_json(f"{_gitlab_api()}/projects/{urllib.parse.quote(path, safe='')}?license=true")
            if code == 404:
                status.found = False
            elif code != 200:
                status.error = f"HTTP {code}"
            else:
                status.archived = bool(data.get("archived"))
                key = (data.get("license") or {}).get("key")
                status.license = GITLAB_LICENSES.get(key or "", key)
                status.pushed_at = data.get("last_activity_at")
                full = data.get("path_with_namespace")
                if full and full.lower() != path.lower():
                    status.canonical = f"https://gitlab.com/{full}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        status.error = f"réseau : {getattr(exc, 'reason', exc)}"
    return status


class RepoCache:
    def __init__(self, path: Path | None = None, ttl: int = CACHE_TTL):
        self.path = path or userdata.cache_dir() / "depots.json"
        self.ttl = ttl
        try:
            self.data: dict[str, dict] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, url: str) -> RepoStatus | None:
        raw = self.data.get(url)
        if not raw or time.time() - raw.get("checked_at", 0) > self.ttl:
            return None
        return RepoStatus(**raw)

    def put(self, status: RepoStatus) -> None:
        if status.usable:  # une erreur réseau n'est pas mise en cache
            self.data[status.url] = asdict(status)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        except OSError:
            pass


# ----------------------------------------------------------------- contrôles
def _age_days(when: str | None, today: date) -> int | None:
    if not when:
        return None
    try:
        d = datetime.fromisoformat(when.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return (datetime(today.year, today.month, today.day, tzinfo=UTC) - d).days


def offline_findings(catalog: Catalog, today: date, stale_days: int = STALE_DAYS) -> list[Finding]:
    from .landscape import load_index
    out: list[Finding] = []
    names = {e["name"].lower() for e in load_index(catalog.index_path)}
    provided = {cap for t in catalog.curated() for cap in t.provides}
    for message in catalog.errors:
        out.append(Finding("—", "Catalogue personnel", "user-error", TO_FIX, message))
    for t in catalog.curated():
        if t.landscape and t.landscape.maturity == "archived" and t.lifecycle == "active":
            out.append(Finding(t.id, t.name, "landscape-archived", TO_FIX,
                               "le Landscape classe le projet comme archivé, la fiche le dit actif.",
                               _archive_fix(today, "Projet archivé selon le CNCF Landscape"), "marquer la fiche archivée"))
        if t.landscape_name and t.landscape_name.lower() not in names and names:
            out.append(Finding(t.id, t.name, "landscape-gone", WATCH,
                               f"l'entrée « {t.landscape_name} » n'apparaît plus dans l'index du Landscape."))
        for attr, label in (("replacements", "remplaçant"), ("alternatives", "alternative"),
                            ("alternatives_outside_k8s", "alternative hors Kubernetes")):
            for ref in getattr(t, attr):
                if ref not in catalog:
                    out.append(Finding(t.id, t.name, "broken-ref", TO_FIX, f"{label} « {ref} » inexistant dans le catalogue."))
        for cap in t.requires:
            if cap not in provided:
                out.append(Finding(t.id, t.name, "orphan-capability", WATCH,
                                   f"requiert « {cap} », qu'aucune fiche ne fournit."))
        age = _age_days(t.verified, today)
        if t.verified is None or (age is not None and age > stale_days):
            when = f"vérifiée le {t.verified}" if t.verified else "jamais vérifiée"
            out.append(Finding(t.id, t.name, "stale", INFO, f"fiche {when} : à relire.",
                               {"verified": today.isoformat()}, "marquer la fiche comme relue aujourd'hui"))
        if t.license == "unknown":
            out.append(Finding(t.id, t.name, "license-unknown", WATCH,
                               "licence inconnue : la politique « open source uniquement » écarte cette brique."))
        if t.is_oss and t.repo is None and t.repo_url is None:
            out.append(Finding(t.id, t.name, "no-source", INFO,
                               "open source sans dépôt connu : archivage et licence ne peuvent pas être suivis."))
    return out


def _archive_fix(today: date, why: str) -> dict:
    return {"lifecycle": "archived", "lifecycle_note": f"{why} (constaté le {today.isoformat()})."}


def repo_findings(tool: Tool, st: RepoStatus, today: date, inactive_days: int = INACTIVE_DAYS) -> list[Finding]:
    out: list[Finding] = []
    if not st.found:
        return [Finding(tool.id, tool.name, "repo-missing", WATCH, f"dépôt introuvable : {st.url} (supprimé ou devenu privé).")]
    if st.archived and tool.lifecycle == "active":
        out.append(Finding(tool.id, tool.name, "archived", TO_FIX, f"le dépôt {st.url} est archivé.",
                           _archive_fix(today, "Dépôt archivé"), "marquer la fiche archivée"))
    remote = normalize_license(st.license)
    mine = normalize_license(tool.license)
    if remote and mine and remote != mine and tool.license != "proprietary":
        level = TO_FIX if (tool.is_oss and remote not in OSS_LICENSES) else WATCH
        why = " ; elle ne compte plus comme open source" if level == TO_FIX else ""
        out.append(Finding(tool.id, tool.name, "license", level,
                           f"licence du dépôt : {remote}, fiche : {tool.license}{why}.",
                           {"license": remote}, f"passer la licence à {remote}"))
    age = _age_days(st.pushed_at, today)
    if not st.archived and age is not None and age > inactive_days:
        out.append(Finding(tool.id, tool.name, "inactive", WATCH,
                           f"aucune activité sur le dépôt depuis {age // 30} mois ({st.pushed_at[:10]})."))
    if st.canonical and st.canonical.lower() != (tool.repo_url or "").lower().rstrip("/"):
        out.append(Finding(tool.id, tool.name, "moved", INFO, f"dépôt déplacé vers {st.canonical}.",
                           {"repo": st.canonical}, "mettre à jour l'adresse du dépôt"))
    return out


def check_catalog(catalog: Catalog, network: bool = True, today: date | None = None,
                  cache: RepoCache | None = None, token: str | None = None,
                  progress: Callable[[int, int], None] | None = None, refresh: bool = False,
                  max_workers: int = 8) -> Report:
    today = today or date.today()
    report = Report(network=network)
    tools = catalog.curated()
    report.checked = len(tools)
    report.findings.extend(offline_findings(catalog, today))
    if network:
        cache = cache or RepoCache()
        token = token if token is not None else github_token()
        by_url: dict[str, list[Tool]] = {}
        for t in tools:
            if t.repo_url and parse_repo(t.repo_url):
                by_url.setdefault(t.repo_url.rstrip("/"), []).append(t)
        urls = sorted(by_url)
        statuses: dict[str, RepoStatus] = {}
        todo = []
        for u in urls:
            cached = None if refresh else cache.get(u)
            if cached:
                statuses[u] = cached
            else:
                todo.append(u)
        done = len(statuses)
        if progress:
            progress(done, len(urls))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for st in pool.map(lambda u: fetch_repo(u, token), todo):
                statuses[st.url] = st
                cache.put(st)
                done += 1
                if progress:
                    progress(done, len(urls))
        cache.save()
        for u in urls:
            st = statuses[u]
            if not st.usable:
                report.repos_failed.append(f"{u} ({st.error})")
                continue
            report.repos_checked += 1
            for t in by_url[u]:
                report.findings.extend(repo_findings(t, st, today))
    order = {lv: i for i, lv in enumerate(LEVELS)}
    report.findings.sort(key=lambda f: (order[f.level], f.tool_name.lower(), f.kind))
    return report


def affected_bricks(project, finding: Finding) -> int:
    return sum(1 for _, b in project.all_bricks() if b.tool == finding.tool_id)


