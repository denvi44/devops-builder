# SPDX-License-Identifier: Apache-2.0
"""Défauts relevés par l'essai UX/UI : erreurs d'écriture, double-clic, mode sans application, assistant, recherche."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from devops_builder.catalog import DATA_DIR, default_catalog
from devops_builder.model import Project

EXAMPLES = DATA_DIR / "examples"


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


def load(win, name: str) -> None:
    win._load(Project.load(EXAMPLES / name), None)


def test_enregistrer_dans_un_dossier_inexistant_previent(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[1]))
    window.path = tmp_path / "absent" / "x.devops.yaml"
    assert window.save() is False
    assert shown == ["Enregistrement impossible"]


def test_double_clic_sur_un_diagnostic_n_applique_aucune_correction(window):
    load(window, "01-web-hote-docker.devops.yaml")
    before = len(window.project.all_bricks()) if hasattr(window.project, "all_bricks") else None
    tree = window.diagnostics.tree
    applied = []
    window.diagnostics.actionRequested.connect(applied.append)
    for i in range(tree.topLevelItemCount()):
        window.diagnostics._activated(tree.topLevelItem(i))
    assert applied == []
    if before is not None:
        assert len(window.project.all_bricks()) == before


def test_plateforme_seule_ne_reclame_pas_de_dossier(window):
    from devops_builder.model import Severity
    from devops_builder.ui.accueil import next_step
    load(window, "05-labo-hote-docker.devops.yaml")
    assert window.app_btn.text() == "Plateforme seule"
    assert next_step(window.project, [], Severity.BLOCKING)[2] == "generer"


def test_fenetre_utilisable_a_1024(window):
    assert window.minimumSizeHint().width() <= 1024


def test_regles_dans_un_dialogue_defilant(window, monkeypatch):
    from PySide6.QtWidgets import QDialog, QTextBrowser
    seen = {}

    def fake_exec(self):
        seen["browser"] = self.findChild(QTextBrowser)
        seen["height"] = self.height()
        return 0
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    window.show_rules()
    assert seen["browser"] is not None and seen["height"] <= 700


def test_assistant_normalise_le_nom_d_image(window):
    from devops_builder.ui.wizard import StarterWizard
    w = StarterWizard(window.catalog, window.engine)
    w.w_image.setText("Mon App !! É")
    w._normalize_image()
    assert w.w_image.text() == "mon-app-e"
    w.w_image.setText("Autre  Nom")
    assert w.collect().image_name == "autre-nom"


def test_assistant_oublie_le_cloud_en_changeant_d_hebergement(window):
    from devops_builder.ui.wizard import StarterWizard
    w = StarterWizard(window.catalog, window.engine)
    keys = {b.property("key"): b for b in w.g_hosting.buttons()}
    assert "docker-host" in keys and "kubernetes-managed" in keys
    keys["kubernetes-managed"].setChecked(True)
    w.w_cloud.setCurrentIndex(max(0, w.w_cloud.count() - 1))
    keys["docker-host"].setChecked(True)
    assert w.w_cloud.currentData() is None


@pytest.mark.parametrize("saisie, attendu", [
    ("kubernets", "kubescape"), ("dokcer", "docker-compose"), ("graphana", "grafana"), ("terrafrom", "terraform"),
    ("bdd", "postgresql"), ("supervision", "prometheus"), ("sécurité", "trivy"), ("sécurité", "gitleaks"),
    ("authentification", "keycloak"), ("mot de passe", "openbao"), ("proxy inverse", "traefik"), ("SSO", "keycloak"),
])
def test_recherche_tolere_fautes_synonymes_et_etapes(saisie, attendu):
    ids = [t.id for t in default_catalog().search(saisie)]
    assert attendu in ids, ids


def test_recherche_termes_courts_en_mots_entiers():
    ids = {t.id for t in default_catalog().search("SSO")}
    assert "azure-vnet" not in ids


@pytest.mark.parametrize("option, valeur", [("--envs", "bidon"), ("--hosting", "bidon")])
def test_init_refuse_une_valeur_inconnue_proprement(tmp_path, option, valeur):
    r = subprocess.run([sys.executable, "-m", "devops_builder", "init", str(tmp_path), "-o", str(tmp_path / "x.devops.yaml"),
                        option, valeur], capture_output=True, text=True, cwd=Path(__file__).parents[1])
    assert r.returncode == 2 and "Traceback" not in r.stderr
    assert not (tmp_path / "x.devops.yaml").exists()
