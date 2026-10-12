# SPDX-License-Identifier: Apache-2.0
"""Lot 4 : entretien du catalogue, catalogue personnel, rafraîchissement du Landscape.

Chaque test travaille dans son propre dossier utilisateur (DEVOPS_BUILDER_HOME) ; l'API
GitHub est remplacée par un petit serveur local qui répond comme elle.
"""

from __future__ import annotations

import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

from devops_builder import catalog_edit, health, landscape, userdata
from devops_builder.catalog import DATA_DIR, build_catalog, reload_default_catalog
from devops_builder.cli import main as cli
from devops_builder.generators import generate
from devops_builder.model import Project
from devops_builder.rules import RuleEngine

TODAY = date(2026, 10, 9)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVOPS_BUILDER_HOME", str(tmp_path / "home"))
    yield tmp_path / "home"
    reload_default_catalog()


def user_catalog():
    return build_catalog(DATA_DIR, user_dir=userdata.catalog_dir(), index_path=landscape.current_index_path())


def write_fiche(name: str, data) -> Path:
    path = userdata.user_fiches_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def keptn_entry():
    return next(e for e in landscape.load_index() if e["name"] == "Keptn")


# ------------------------------------------------------------------ catalogue personnel
def test_fiche_personnelle_chargee_et_controlee(home):
    write_fiche("outil.yaml", {"id": "mon-outil", "name": "Mon outil", "stage": "test", "license": "MIT"})
    write_fiche("casse.yaml", {"id": "casse", "name": "Cassé", "stage": "nulle-part"})
    write_fiche("doublon.yaml", {"id": "trivy", "name": "Autre Trivy", "stage": "security"})
    write_fiche("lsc.yaml", {"id": "lsc-truc", "name": "Truc", "stage": "build"})
    (userdata.user_fiches_dir() / "illisible.yaml").write_text("id: [\n", encoding="utf-8")
    c = user_catalog()
    assert c["mon-outil"].origin == "utilisateur" and c["mon-outil"].curated
    assert c["trivy"].origin == "livrée"
    errors = "\n".join(c.errors)
    assert "étape inconnue « nulle-part »" in errors
    assert "déjà pris par « Trivy »" in errors
    assert "lsc-truc" in errors and "illisible.yaml" in errors
    assert "casse" not in c.tools


def test_import_depuis_le_landscape_remplace_l_entree_brute(home):
    before = user_catalog()
    assert "lsc-keptn" in before
    data = catalog_edit.draft_from_landscape(keptn_entry(), before, TODAY)
    assert data["id"] == "keptn" and data["license"] == "unknown"
    assert data["lifecycle"] == "archived"          # archivé selon le Landscape : signalé dès l'import
    catalog_edit.save_fiche(data, before)
    after = user_catalog()
    assert after.get("lsc-keptn").id == "keptn"     # un projet qui utilisait l'entrée brute suit la fiche
    assert after["keptn"].landscape and after["keptn"].landscape.subcategory
    assert sum(1 for t in after.tools.values() if t.name == "Keptn") == 1


def test_projet_avec_ancienne_entree_brute(home):
    catalog_edit.save_fiche(catalog_edit.draft_from_landscape(keptn_entry(), user_catalog(), TODAY), user_catalog())
    c = user_catalog()
    p = Project(name="t", target="kubernetes")
    for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", "k3s", "helm"):
        p.add(t, c[t].stage)
    p.add("lsc-keptn", "build")
    diags = RuleEngine(c).evaluate(p)
    assert any("Keptn" in d.message for d in diags)   # cycle de vie : archivé
    generate(p, c)


def test_validation_d_une_fiche_saisie(home):
    c = user_catalog()
    tool, problems = catalog_edit.validate_fiche({"id": "Mauvais Id", "name": "x", "stage": "build"}, c)
    assert tool is None and "invalide" in problems[0]
    tool, problems = catalog_edit.validate_fiche({"id": "x-ok", "name": "x", "stage": "build",
                                                  "replacements": ["inexistant"]}, c)
    assert "inexistant" in problems[0]
    tool, problems = catalog_edit.validate_fiche({"id": "x-ok", "name": "x"}, c)
    assert tool is None and problems
    tool, problems = catalog_edit.validate_fiche({"id": "x-ok", "name": "x", "stage": "build"}, c)
    assert tool is not None and problems == []


def test_modifier_et_supprimer_une_fiche_personnelle(home):
    c = user_catalog()
    catalog_edit.save_fiche({"id": "outil-a", "name": "A", "stage": "build"}, c)
    c = user_catalog()
    data = catalog_edit.tool_to_data(c["outil-a"])
    data.update(id="outil-b", description="renommé")
    catalog_edit.save_fiche(data, c, editing="outil-a")
    c = user_catalog()
    assert "outil-a" not in c.tools and c["outil-b"].description == "renommé"
    assert catalog_edit.delete_fiche("outil-b")
    assert "outil-b" not in user_catalog().tools


# ------------------------------------------------------------------ corrections
def test_corrections_des_fiches_livrees(home):
    catalog_edit.write_corrections({"trivy": {"license": "MIT", "verified": "2026-01-01"}})
    c = user_catalog()
    assert c["trivy"].license == "MIT" and c["trivy"].corrections == {"license": "Apache-2.0", "verified": "2026-10-08"}
    assert c["trivy"].param_schema == build_catalog()["trivy"].param_schema
    assert build_catalog()["trivy"].license == "Apache-2.0"     # les fichiers livrés ne changent pas
    assert catalog_edit.remove_correction("trivy")
    assert user_catalog()["trivy"].corrections == {}


def test_correction_invalide_signalee(home):
    path = userdata.corrections_file()
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({"trivy": {"stage": "deploy"}, "fantome": {"license": "MIT"},
                                    "helm": {"lifecycle": "peut-être"}}), encoding="utf-8")
    c = user_catalog()
    errors = "\n".join(c.errors)
    assert "non corrigeable" in errors and "fantome" in errors and "helm" in errors
    assert c["trivy"].stage == "security" and c["helm"].lifecycle == "active"
    with pytest.raises(ValueError):
        catalog_edit.write_corrections({"trivy": {"stage": "deploy"}})


# ------------------------------------------------------------------ contrôles hors ligne
def test_controles_hors_ligne(home):
    catalog_edit.write_corrections({"trivy": {"verified": "2025-01-10"}, "helm": {"replacements": ["disparu"]}})
    write_fiche("x.yaml", {"id": "outil-x", "name": "Outil X", "stage": "build", "license": "unknown"})
    report = health.check_catalog(user_catalog(), network=False, today=TODAY)
    kinds = {(f.tool_id, f.kind) for f in report.findings}
    assert ("trivy", "stale") in kinds and ("helm", "broken-ref") in kinds and ("outil-x", "license-unknown") in kinds
    stale = next(f for f in report.findings if f.kind == "stale")
    assert stale.fix == {"verified": "2026-10-09"}
    assert report.by_level(health.TO_FIX)[0].kind == "broken-ref"   # trié par gravité
    assert "hors ligne" in report.summary()


def test_catalogue_livre_sans_anomalie_hors_ligne():
    report = health.check_catalog(build_catalog(), network=False, today=TODAY)
    assert [(f.tool_id, f.message) for f in report.findings if f.level != health.INFO] == []


# ------------------------------------------------------------------ contrôles en ligne
class FakeForge(BaseHTTPRequestHandler):
    calls: list[str] = []
    auth: list[str | None] = []
    repos: dict[str, tuple[int, dict]] = {}

    def do_GET(self):  # noqa: N802
        FakeForge.calls.append(self.path)
        FakeForge.auth.append(self.headers.get("Authorization"))
        code, body = FakeForge.repos.get(self.path.split("?")[0], (404, {"message": "Not Found"}))
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


@pytest.fixture
def forge(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), FakeForge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("DEVOPS_BUILDER_GITHUB_API", base)
    monkeypatch.setenv("DEVOPS_BUILDER_GITLAB_API", base + "/gitlab")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    FakeForge.calls = []
    FakeForge.repos = {}
    yield FakeForge
    server.shutdown()


def gh(full_name: str, license: str | None = "Apache-2.0", archived: bool = False, pushed: str = "2026-09-30T10:00:00Z"):
    return 200, {"full_name": full_name, "archived": archived, "pushed_at": pushed,
                 "license": {"spdx_id": license} if license else None}


def _catalog_with(tools: dict[str, str]):
    """Catalogue réduit aux fiches demandées (identifiant → dépôt), pour maîtriser les requêtes."""
    c = build_catalog()
    keep = {tid: c.tools[tid] for tid in tools}
    for tid, repo in tools.items():
        keep[tid] = keep[tid].model_copy(update={"repo": repo})
    c.tools = keep
    return c


def test_depots_archive_licence_renomme_introuvable_inactif(home, forge):
    forge.repos = {
        "/repos/moby/buildkit": gh("moby/buildkit", archived=True),
        "/repos/hashicorp/terraform": gh("hashicorp/terraform", license="BUSL-1.1"),
        "/repos/aquasecurity/trivy": gh("aquasecurity/trivy", license="AGPL-3.0"),
        "/repos/anchore/syft": gh("anchore/syft-renamed"),
        "/repos/anchore/grype": gh("anchore/grype", pushed="2024-01-01T00:00:00Z"),
        "/gitlab/projects/groupe%2Fprojet": (200, {"path_with_namespace": "groupe/projet", "archived": True,
                                                    "license": {"key": "mit"}, "last_activity_at": "2026-09-01"}),
    }
    c = _catalog_with({"buildkit": "https://github.com/moby/buildkit", "terraform": "https://github.com/hashicorp/terraform",
                       "trivy": "https://github.com/aquasecurity/trivy", "syft": "https://github.com/anchore/syft",
                       "grype": "https://github.com/anchore/grype", "gitleaks": "https://github.com/gitleaks/disparu",
                       "semgrep": "https://gitlab.com/groupe/projet"})
    report = health.check_catalog(c, today=TODAY, token="", cache=health.RepoCache(home / "c.json"))
    by = {(f.tool_id, f.kind): f for f in report.findings}
    assert by[("buildkit", "archived")].level == health.TO_FIX
    assert by[("buildkit", "archived")].fix["lifecycle"] == "archived"
    assert ("terraform", "license") not in by                    # BUSL-1.1 = BSL-1.1 de la fiche
    trivy = by[("trivy", "license")]
    assert trivy.level == health.WATCH and trivy.fix == {"license": "AGPL-3.0"}
    assert by[("syft", "moved")].fix == {"repo": "https://github.com/anchore/syft-renamed"}
    assert by[("grype", "inactive")].level == health.WATCH
    assert by[("gitleaks", "repo-missing")].level == health.WATCH
    assert by[("semgrep", "archived")] and ("semgrep", "license") in by   # GitLab : MIT ≠ LGPL-2.1
    assert report.repos_checked == 7 and report.repos_failed == []


def test_licence_devenue_proprietaire_est_a_corriger(home, forge):
    forge.repos = {"/repos/aquasecurity/trivy": gh("aquasecurity/trivy", license="BUSL-1.1")}
    c = _catalog_with({"trivy": "https://github.com/aquasecurity/trivy"})
    report = health.check_catalog(c, today=TODAY, token="", cache=health.RepoCache(home / "c.json"))
    (f,) = [f for f in report.findings if f.kind == "license"]
    assert f.level == health.TO_FIX and "open source" in f.message


def test_cache_et_limite_d_api(home, forge):
    forge.repos = {"/repos/moby/buildkit": gh("moby/buildkit"),
                   "/repos/containers/buildah": (403, {"message": "API rate limit exceeded"})}
    c = _catalog_with({"buildkit": "https://github.com/moby/buildkit", "buildah": "https://github.com/containers/buildah"})
    cache = health.RepoCache(home / "c.json")
    first = health.check_catalog(c, today=TODAY, token="", cache=cache)
    assert first.repos_checked == 1 and "rate limit" in first.repos_failed[0]
    calls = len(forge.calls)
    second = health.check_catalog(c, today=TODAY, token="", cache=health.RepoCache(home / "c.json"))
    assert len(forge.calls) == calls + 1        # buildkit vient du cache, buildah est redemandé
    assert second.repos_checked == 1
    health.check_catalog(c, today=TODAY, token="", cache=health.RepoCache(home / "c.json"), refresh=True)
    assert len(forge.calls) == calls + 3


def test_jeton_transmis(home, forge, monkeypatch):
    forge.repos = {"/repos/moby/buildkit": gh("moby/buildkit")}
    health.fetch_repo("https://github.com/moby/buildkit", "jeton-test")
    assert forge.auth[-1] == "Bearer jeton-test"
    monkeypatch.setenv("GITHUB_TOKEN", "depuis-env")
    assert health.github_token() == "depuis-env"


def test_appliquer_les_corrections(home, forge):
    forge.repos = {"/repos/moby/buildkit": gh("moby/buildkit", archived=True)}
    write_fiche("perso.yaml", {"id": "perso", "name": "Perso", "stage": "build", "license": "MIT",
                               "repo": "https://github.com/moby/buildkit"})
    c = user_catalog()
    c.tools = {k: v for k, v in c.tools.items() if k in ("perso", "buildkit")}
    c.tools["buildkit"] = c.tools["buildkit"].model_copy(update={"repo": "https://github.com/moby/buildkit"})
    report = health.check_catalog(c, today=TODAY, token="", cache=health.RepoCache(home / "c.json"))
    fixes = [(f.tool_id, f.fix) for f in report.findings if f.kind == "archived"]
    assert {t for t, _ in fixes} == {"perso", "buildkit"}
    catalog_edit.apply_fixes(fixes, user_catalog())
    after = user_catalog()
    assert after["buildkit"].lifecycle == "archived" and after["buildkit"].corrections["lifecycle"] == "active"
    assert after["perso"].lifecycle == "archived" and after["perso"].corrections == {}   # écrit dans la fiche
    assert "lifecycle: archived" in (userdata.user_fiches_dir() / "perso.yaml").read_text()


def test_parse_repo():
    assert health.parse_repo("https://github.com/a/b.git") == ("github", "a/b")
    assert health.parse_repo("https://github.com/a/b/tree/main/sub") == ("github", "a/b")
    assert health.parse_repo("https://gitlab.com/g/s/p") == ("gitlab", "g/s/p")
    assert health.parse_repo("https://codeberg.org/a/b") is None
    assert health.normalize_license("AGPL-3.0-only") == "AGPL-3.0"
    assert health.normalize_license("NOASSERTION") is None


# ------------------------------------------------------------------ Landscape
def _landscape_yaml(n: int = 120, archived: str | None = None, extra: str | None = None) -> str:
    items = [{"name": f"Outil {i}", "repo_url": f"https://github.com/o/outil-{i}", "homepage_url": "https://x"}
             for i in range(n)]
    items[0]["name"] = "Keptn"
    if archived:
        items[1] = {"name": archived, "project": "archived", "repo_url": "https://github.com/o/a"}
    if extra:
        items.append({"name": extra, "repo_url": "https://github.com/o/nouveau"})
    return yaml.safe_dump({"landscape": [
        {"name": "App Definition and Development", "subcategories": [
            {"name": "Continuous Integration & Delivery", "items": items}]},
        {"name": "CNCF Members", "subcategories": [{"name": "Platinum", "items": [{"name": "Exclu"}]}]},
    ]})


def test_rafraichir_le_landscape(home, tmp_path):
    src = tmp_path / "landscape.yml"
    src.write_text(_landscape_yaml(archived="Outil 1", extra="Tout Nouveau"), encoding="utf-8")
    diff, path = landscape.refresh(src)
    assert path == userdata.landscape_index() and landscape.current_index_path() == path
    assert "Tout Nouveau" in diff.added and "Exclu" not in diff.added
    assert diff.newly_archived == [] and len(diff.removed) > 900          # index livré bien plus grand
    c = reload_default_catalog()
    assert "lsc-tout-nouveau" in c
    src.write_text(_landscape_yaml(archived="Outil 2"), encoding="utf-8")
    diff2, _ = landscape.refresh(src)
    assert diff2.newly_archived == ["Outil 2"] and diff2.removed == ["Outil 1", "Tout Nouveau"]
    assert landscape.reset() and landscape.current_index_path() == landscape.PACKAGED_INDEX


def test_landscape_trop_court_ou_invalide(home, tmp_path):
    src = tmp_path / "landscape.yml"
    src.write_text(_landscape_yaml(n=5), encoding="utf-8")
    with pytest.raises(ValueError, match="anormalement court"):
        landscape.refresh(src)
    src.write_text("autre: chose\n", encoding="utf-8")
    with pytest.raises(ValueError, match="landscape.yml"):
        landscape.refresh(src)
    assert not userdata.landscape_index().exists()


def test_index_livre_reconstruit_a_l_identique():
    """Le module du paquet reconstruit le même index que l'outil des versions précédentes."""
    index = landscape.load_index(landscape.PACKAGED_INDEX)
    assert len(index) > 1000 and all({"name", "category", "subcategory"} <= set(e) for e in index)


# ------------------------------------------------------------------ ligne de commande
def test_cli_import_controle_et_refresh(home, tmp_path, capsys):
    assert cli(["catalog-import", "Keptn", "--offline"]) == 0
    assert (userdata.user_fiches_dir() / "keptn.yaml").exists()
    assert cli(["catalog-import", "Keptn", "--offline"]) == 1          # déjà une fiche
    assert cli(["catalog-import", "Keptin", "--offline"]) == 1
    assert "Keptn" in capsys.readouterr().out                          # nom proche proposé
    assert cli(["catalog-check", "--offline"]) == 0                    # archivée dès l'import : rien à corriger
    report = tmp_path / "rapport.md"
    assert cli(["catalog-check", "--offline", "--report", str(report)]) == 0
    assert "# Entretien du catalogue" in report.read_text()
    src = tmp_path / "landscape.yml"
    src.write_text(_landscape_yaml(), encoding="utf-8")
    assert cli(["landscape-refresh", "--source", str(src)]) == 0
    assert cli(["landscape-refresh", "--reset"]) == 0


def test_cli_check_signale_a_corriger(home, capsys):
    catalog_edit.write_corrections({"helm": {"replacements": ["disparu"]}})
    assert cli(["catalog-check", "--offline"]) == 1
    assert "disparu" in capsys.readouterr().out
