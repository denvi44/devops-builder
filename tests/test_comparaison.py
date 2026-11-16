# SPDX-License-Identifier: Apache-2.0
"""Comparaison avant / après de deux architectures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from devops_builder.catalog import DATA_DIR, default_catalog
from devops_builder.comparaison import compare
from devops_builder.model import Project
from devops_builder.rules import RuleEngine

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
EXAMPLE = DATA_DIR / "examples" / "01-web-hote-docker.devops.yaml"
ROOT = Path(__file__).parents[1]


def example() -> Project:
    return Project.load(EXAMPLE)


def sans_trivy(p: Project) -> Project:
    p.stages["security"] = [b for b in p.stages["security"] if b.tool != "trivy"]
    return p


def test_projets_identiques():
    r = compare(example(), example(), CATALOG, ENGINE)
    assert r.identical and r.summary() == "Aucune différence." and not r.files


def test_brique_retiree_et_diagnostic_resolu():
    r = compare(example(), sans_trivy(example()), CATALOG, ENGINE, files=False)
    assert [(b.tool, b.kind) for b in r.bricks] == [("trivy", "retirée")]
    assert "R23" in {d.rule_id for d in r.resolved_diagnostics} and not r.new_diagnostics
    assert not r.files_compared and "Trivy" in r.to_markdown()


def test_reglages_environnements_et_parametres():
    b = example()
    b.target = "vm"
    b.app.port = 9000
    b.environments[0].approval = True
    gitlab = next(x for _, x in b.all_bricks() if x.tool == "gitlab-ci")
    gitlab.params = {**gitlab.params, "runner_tags": "docker"}
    r = compare(example(), b, CATALOG, ENGINE, files=False)
    text = "\n".join([*r.settings, *r.environments])
    assert "Cible d'hébergement" in text and "Port de l'application : 8000 → 9000" in text
    assert "approbation : non → oui" in text
    assert any(c.kind == "modifiée" and c.tool == "gitlab-ci" for c in r.bricks)


def test_fichiers_generes_compares():
    r = compare(example(), sans_trivy(example()), CATALOG, ENGINE)
    changed = {f.path: f for f in r.files}
    assert ".gitlab-ci.yml" in changed and changed[".gitlab-ci.yml"].removed > 0
    assert "devops-builder.yaml" not in changed and r.to_dict()["files"]


def test_une_modification_qui_introduit_un_blocage():
    b = example()
    b.stages["build"] = []          # plus de CI : l'étape de déploiement n'a plus rien à livrer
    r = compare(example(), b, CATALOG, ENGINE, files=False)
    assert r.after_blocking >= r.before_blocking
    assert r.introduces_blocking == any(d.severity.value == "bloquant" for d in r.new_diagnostics)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "devops_builder", "compare", *args], capture_output=True, text=True,
                          cwd=ROOT)


@pytest.fixture
def paires(tmp_path):
    a, b = tmp_path / "a.devops.yaml", tmp_path / "b.devops.yaml"
    example().save(a)
    sans_trivy(example()).save(b)
    return a, b


def test_cli_markdown_json_et_rapport(paires, tmp_path):
    a, b = paires
    r = run_cli(str(a), str(b), "--no-files")
    assert r.returncode == 0 and "Trivy" in r.stdout
    data = json.loads(run_cli(str(a), str(b), "--no-files", "--json").stdout)
    assert data["command"] == "compare" and data["bricks"][0]["change"] == "retirée" and data["files"] is None
    out = tmp_path / "rapport.md"
    r = run_cli(str(a), str(b), "--no-files", "-o", str(out))
    assert r.returncode == 0 and out.read_text(encoding="utf-8").startswith("# Comparaison")


def test_cli_fichier_absent_et_ecriture_impossible(paires, tmp_path):
    a, _ = paires
    assert run_cli(str(a), str(tmp_path / "absent.yaml")).returncode == 2
    r = run_cli(str(a), str(a), "--no-files", "-o", str(tmp_path / "x" / "r.md"))
    assert r.returncode == 2 and "Écriture impossible" in r.stderr


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path_factory.mktemp("home"))
    from devops_builder.ui.app import create_window
    app, win = create_window(["devops-builder"])
    win.show()
    app.processEvents()
    yield win
    win.undo_stack.setClean()
    win.close()
    if home is not None:
        os.environ["HOME"] = home


def test_interface_point_de_depart_et_dialogue(window, monkeypatch):
    from PySide6.QtWidgets import QDialog, QTextBrowser
    window._load(example(), None)
    sans_trivy(window.project)          # modification faite dans l'interface
    seen = {}

    def fake_exec(self):
        seen["text"] = self.findChild(QTextBrowser).toPlainText()
        return 0
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    window.compare_baseline()
    assert "Trivy" in seen["text"] and "retirée" in seen["text"]
    window.set_baseline()
    window.compare_baseline()
    assert "Aucune différence" in seen["text"]
