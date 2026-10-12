"""Lot 0.16 : contrat de la ligne de commande (codes de sortie, sortie --json, --version)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from devops_builder import __version__
from devops_builder.cli import JSON_SCHEMA
from devops_builder.cli import main as cli

ROOT = Path(__file__).parent.parent
EXAMPLE = str(ROOT / "devops_builder" / "data" / "examples" / "01-web-hote-docker.devops.yaml")


def _json(capsys) -> dict:
    data = json.loads(capsys.readouterr().out)
    assert data["schema"] == JSON_SCHEMA and data["version"] == __version__
    return data


def test_version_alignee_sur_le_paquet(capsys):
    pyproject = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    assert __version__ == pyproject
    with pytest.raises(SystemExit) as exc:
        cli(["--version"])
    assert exc.value.code == 0 and capsys.readouterr().out.strip() == f"devops-builder {__version__}"


def test_check_json(capsys):
    assert cli(["check", EXAMPLE, "--json"]) == 0
    data = _json(capsys)
    assert data["command"] == "check" and data["ok"] and data["blocking"] == 0
    assert {"rule", "severity", "family", "message", "bricks", "actions"} <= set(data["diagnostics"][0])


def test_check_bloquant_code_1(tmp_path, capsys):
    from test_data import project

    bad = tmp_path / "p.devops.yaml"
    project("docker-host", "github", "github-actions", "buildkit").save(bad)  # R26 : rien à déployer
    assert cli(["check", str(bad), "--json"]) == 1
    data = _json(capsys)
    assert not data["ok"] and data["blocking"] >= 1


@pytest.mark.parametrize("content, message", [
    (None, "introuvable"),
    ("name: [", "YAML invalide"),
    ("format_version: 99\nname: x\n", "version plus récente"),
])
def test_fichier_illisible_code_2(tmp_path, capsys, content, message):
    path = tmp_path / "p.devops.yaml"
    if content is not None:
        path.write_text(content)
    for cmd in (["check", str(path)], ["generate", str(path), "-o", str(tmp_path / "out")],
                ["validate", str(path), "--offline"]):
        assert cli(cmd) == 2
        err = capsys.readouterr().err
        assert message in err


def test_generate_json_a_blanc_puis_ecrit(tmp_path, capsys):
    out = tmp_path / "out"
    assert cli(["generate", EXAMPLE, "-o", str(out), "--dry-run", "--json"]) == 0
    data = _json(capsys)
    assert data["dry_run"] and data["written"] == 0 and not out.exists()
    paths = {f["path"]: f for f in data["files"]}
    assert paths["PIPELINE.md"]["status"] and {"added", "removed", "selected", "deletion"} <= set(paths["PIPELINE.md"])
    assert cli(["generate", EXAMPLE, "-o", str(out), "--json"]) == 0
    data = _json(capsys)
    assert data["written"] == len([p for p in out.rglob("*") if p.is_file() and ".devops-builder" not in p.parts])


def test_validate_json(capsys):
    code = cli(["validate", EXAMPLE, "--offline", "--json"])
    data = _json(capsys)
    assert code == (0 if data["ok"] else 1)
    assert data["results"] and {"id", "label", "status", "files", "seconds", "output", "hint"} <= set(data["results"][0])


def test_champs_inconnus_signales(tmp_path, capsys):
    path = tmp_path / "p.devops.yaml"
    path.write_text(Path(EXAMPLE).read_text() + "revue: equipe-a\n")
    assert cli(["check", str(path)]) == 0
    assert "Champs inconnus de cette version, conservés : revue" in capsys.readouterr().err
    assert cli(["check", str(path), "--json"]) == 0
    assert _json(capsys)["unknown_fields"] == ["revue"]


def test_scan_dossier_absent_code_2(tmp_path):
    assert cli(["scan", str(tmp_path / "absent")]) == 2


def test_documentation_couvre_chaque_commande():
    from devops_builder import cli as module
    doc = (ROOT / "docs" / "ligne-de-commande.md").read_text(encoding="utf-8")
    source = Path(module.__file__).read_text(encoding="utf-8")
    commands = re.findall(r'sub\.add_parser\("([a-z-]+)"', source)
    assert len(commands) >= 10
    for c in commands:
        assert f"`devops-builder {c}" in doc, f"commande {c} absente de docs/ligne-de-commande.md"
    assert f"`schema` : **{JSON_SCHEMA}**" in doc
