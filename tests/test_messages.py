# SPDX-License-Identifier: Apache-2.0
"""Messages d'erreur : en français, avec la cause et la piste de correction, jamais une trace Python."""

from __future__ import annotations

import errno
import subprocess

import pytest
import yaml

from devops_builder.catalog import default_catalog, load_user_fiches
from devops_builder.messages import explain, reason, yaml_problem
from devops_builder.model import Project, ProjectFormatError
from devops_builder.rules import RuleEngine, apply_action

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)


@pytest.mark.parametrize("err, attendu", [
    (PermissionError(errno.EACCES, "Permission denied", "/etc/projet.yaml"), "« /etc/projet.yaml » : accès refusé"),
    (IsADirectoryError(errno.EISDIR, "Is a directory", "/tmp"), "c'est un dossier"),
    (OSError(errno.ENOSPC, "No space left on device"), "Plus de place sur le disque"),
    (FileNotFoundError(errno.ENOENT, "No such file", "git"), "programme « git » introuvable"),
])
def test_erreurs_du_systeme_traduites(err, attendu):
    text = explain(err)
    assert attendu in text and "Errno" not in text


def test_commande_en_echec_et_delai():
    err = subprocess.CalledProcessError(128, ["git", "push", "origin"], stderr="fatal: Authentication failed\n")
    assert explain(err) == "la commande « git push origin » a échoué (code 128) : fatal: Authentication failed"
    assert explain(subprocess.TimeoutExpired(["tofu", "init"], 30)) == "la commande « tofu init » n'a pas répondu en 30 s"


@pytest.mark.parametrize("text, attendu", [
    ("name: x\n\tstages: []\n", "ligne 2, colonne 1 : tabulation interdite"),
    ("name: a: b\n", "« : » inattendu"),
    ("name: x\nstages: [\n", "crochet [ ou accolade { non fermé"),
    ("name: 'x\n", "guillemet non fermé"),
])
def test_yaml_invalide_explique(text, attendu):
    with pytest.raises(yaml.YAMLError) as exc:
        yaml.safe_load(text)
    assert attendu in yaml_problem(exc.value)
    with pytest.raises(ProjectFormatError, match="YAML invalide"):
        Project.from_yaml(text)


def test_fichier_projet_binaire_ou_dossier(tmp_path):
    (tmp_path / "binaire.yaml").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ProjectFormatError, match="n'est pas un fichier texte UTF-8"):
        Project.load(tmp_path / "binaire.yaml")
    with pytest.raises(ProjectFormatError, match="c'est un dossier"):
        Project.load(tmp_path)
    with pytest.raises(FileNotFoundError):  # la ligne de commande en fait « introuvable », code 2
        Project.load(tmp_path / "absent.yaml")


def test_ligne_de_commande_sans_trace(tmp_path, capsys):
    from devops_builder.cli import main
    (tmp_path / "binaire.yaml").write_bytes(b"\xff\xfe")
    assert main(["check", str(tmp_path / "binaire.yaml")]) == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and "UTF-8" in err


def test_fiche_personnelle_illisible_signalee(tmp_path):
    (tmp_path / "abimee.yaml").write_bytes(b"\xff\xfe")
    (tmp_path / "tabulee.yaml").write_text("- id: x\n\tname: y\n")
    tools, errors = load_user_fiches(tmp_path, dict(CATALOG.tools))
    assert not tools and len(errors) == 2
    assert any("UTF-8" in e for e in errors) and any("tabulation" in e for e in errors)


def test_cible_inconnue_bloque_avec_correction():
    p = Project.from_yaml("format_version: 2\nname: x\ntarget: mars\n")
    diags = [d for d in ENGINE.evaluate(p) if d.rule_id == "R53"]
    assert diags and diags[0].severity.value == "bloquant"
    assert "« mars »" in diags[0].message and "Hôte Docker unique" in diags[0].message
    apply_action(p, diags[0].actions[0], CATALOG)
    assert p.target == "docker-host" and not [d for d in ENGINE.evaluate(p) if d.rule_id == "R53"]


def test_raison_seule_quand_le_fichier_est_deja_nomme():
    assert reason(PermissionError(errno.EACCES, "Permission denied", "/x")) == "accès refusé (droits du fichier ou du dossier)"
