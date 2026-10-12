# SPDX-License-Identifier: Apache-2.0
"""Capture hors écran de l'interface (vérification visuelle, documentation).

    QT_QPA_PLATFORM=offscreen python tools/screenshot.py sortie/ [--dark]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings

from devops_builder.catalog import DATA_DIR
from devops_builder.model import Project
from devops_builder.ui.app import create_window


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    dark = "--dark" in sys.argv
    QSettings("DevOpsBuilder", "DevOpsBuilder").setValue("dark", dark)
    app, win = create_window(["devops-builder"])
    win.resize(1600, 960)
    win.show()

    # 1. Exemple de référence, avec une brique sélectionnée
    win._load(Project.load(DATA_DIR / "examples" / "02-api-k3s-gitops.devops.yaml"), None)
    first = win.project.stages["deploy"][1].uid
    win._focus_brick(first)
    app.processEvents()
    suffix = "-dark" if dark else ""
    win.grab().save(str(out / f"01-pipeline{suffix}.png"))

    # 2. Pipeline incohérent : diagnostics et corrections
    p = Project(name="Pipeline à corriger", target="docker-host")
    for t in ["gitlab", "github-actions", "buildkit", "kaniko", "harbor", "argo-cd", "flux", "ecr",
              "ingress-nginx", "prometheus", "thanos"]:
        p.add(t, win.catalog[t].stage)
    win._load(p, None)
    win.diagnostics.tree.setCurrentItem(win.diagnostics.tree.topLevelItem(0))
    app.processEvents()
    win.grab().save(str(out / f"02-diagnostics{suffix}.png"))

    # 3. Pendant un glisser : colonnes compatibles en évidence
    win._load(Project.load(DATA_DIR / "examples" / "01-web-hote-docker.devops.yaml"), None)
    win.canvas.highlight("trivy")
    win._explain_refusal("trivy", "deploy")
    app.processEvents()
    win.grab().save(str(out / f"03-glisser{suffix}.png"))
    win.canvas.clear_highlight()

    win.statusBar().clearMessage()

    # 4. Paramètres typés : une région invalide et une clé mal orthographiée
    p = Project.load(DATA_DIR / "examples" / "03-iac-aws-eks.devops.yaml")
    eks = p.bricks_for("eks")[0]
    eks.params = {"cluster_name": "plateforme-prod", "region": "Paris", "versoin": "1.33"}
    win._load(p, None)
    win._focus_brick(eks.uid)
    win.diagnostics.tree.setCurrentItem(win.diagnostics.tree.topLevelItem(0))
    win._focus_brick(eks.uid)
    app.processEvents()
    win.grab().save(str(out / f"04-parametres{suffix}.png"))

    # 5. Assistant de démarrage : récapitulatif
    from devops_builder.ui.dialogs import ProjectSettingsDialog
    from devops_builder.ui.wizard import StarterWizard

    wiz = StarterWizard(win.catalog, win.engine, win)
    wiz.w_name.setText("Boutique")
    for b in wiz.g_hosting.buttons():
        b.setChecked(b.property("key") == "kubernetes-managed")
    wiz.w_cloud.setCurrentIndex(max(0, wiz.w_cloud.findData("aws")))
    for b in wiz.g_envs.buttons():
        b.setChecked(b.property("key") == "dev-staging-prod")
    wiz.w_db.setCurrentIndex(max(0, wiz.w_db.findData("postgresql")))
    wiz.w_cache.setChecked(True)
    wiz.w_identity.setCurrentIndex(max(0, wiz.w_identity.findData("keycloak")))
    wiz.show()
    for _ in range(4):
        wiz.next()
    app.processEvents()
    wiz.grab().save(str(out / f"05-assistant{suffix}.png"))
    wiz.close()

    # 6. Environnements et promotion
    win._load(Project.load(DATA_DIR / "examples" / "03-iac-aws-eks.devops.yaml"), None)
    dlg = ProjectSettingsDialog(win.project, win, win.catalog)
    dlg.tabs.setCurrentWidget(dlg.envs_editor)
    dlg.envs_editor.list.setCurrentRow(len(win.project.environments) - 1)
    dlg.resize(720, 520)
    dlg.show()
    app.processEvents()
    dlg.grab().save(str(out / f"06-environnements{suffix}.png"))
    dlg.close()

    # 7. Paramètres surchargés pour la production
    eks = win.project.bricks_for("eks")[0]
    win._focus_brick(eks.uid)
    combo = win.properties.env_combo
    combo.setCurrentIndex(combo.count() - 1)
    for _ in range(3):
        app.processEvents()
    win.grab().save(str(out / f"07-surcharges{suffix}.png"))

    # 8 à 10 : validation, différences avant écrasement, export Git
    import subprocess
    import tempfile
    import time

    from devops_builder import sync
    from devops_builder.generators import generate
    from devops_builder.ui.export import GitExportDialog, SyncDialog
    from devops_builder.ui.validation import ValidationDialog

    def wait(cond):
        end = time.monotonic() + 120
        while not cond() and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        app.processEvents()

    result = generate(Project.load(DATA_DIR / "examples" / "03-iac-aws-eks.devops.yaml"), win.catalog)
    val = ValidationDialog(result, win)
    val.network.setChecked(False)
    val.show()
    val.start()
    wait(lambda: val.worker is None)
    val.grab().save(str(out / f"08-validation{suffix}.png"))
    val.close()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sync.apply(sync.plan(result.files, root / "sortie"), root / "sortie")
        (root / "sortie" / "PIPELINE.md").write_text("# Notes de l'équipe\n")
        newer = generate(Project.load(DATA_DIR / "examples" / "03-iac-aws-eks.devops.yaml"), win.catalog)
        newer.files[".gitlab-ci.yml"] = newer.files[".gitlab-ci.yml"].replace("stages:", "# revu\nstages:", 1)
        diff = SyncDialog(newer, root / "sortie", win)
        diff.view.tree.setCurrentItem(diff.view.tree.topLevelItem(0))
        diff.show()
        app.processEvents()
        diff.grab().save(str(out / f"09-differences{suffix}.png"))
        diff.close()

        bare, work = root / "distant.git", root / "commandes"
        git = ["git", "-c", "commit.gpgsign=false", "-c", "push.negotiate=false"]
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
        subprocess.run(["git", "-C", str(bare), "config", "receive.advertisePushOptions", "true"], check=True)
        hook = bare / "hooks" / "post-receive"
        hook.write_text("#!/bin/sh\necho 'View merge request:'\n"
                        "echo '  https://gitlab.exemple.fr/equipe/commandes/-/merge_requests/42'\n")
        hook.chmod(0o755)
        subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work), "remote", "set-url", "--push", "origin", str(bare)], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.name", "Vincent"], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.email", "vincent@exemple.fr"], check=True)
        (work / "app.py").write_text("print('ok')\n")
        subprocess.run([*git, "-C", str(work), "add", "."], check=True)
        subprocess.run([*git, "-C", str(work), "commit", "-q", "-m", "init"], check=True)
        subprocess.run([*git, "-C", str(work), "push", "-q", "origin", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work), "config", "commit.gpgsign", "false"], check=True)
        subprocess.run(["git", "-C", str(work), "config", "push.negotiate", "false"], check=True)
        exp = GitExportDialog(result, win, repo=str(work))
        exp.show()
        exp.start()
        wait(lambda: exp.worker is None)
        exp.grab().save(str(out / f"10-export-git{suffix}.png"))
        exp.close()
    # 11 et 12 : entretien du catalogue et fiche créée depuis le Landscape (dossier personnel jetable)
    import os

    from devops_builder import catalog_edit
    from devops_builder.ui.fiche import open_fiche_dialog
    from devops_builder.ui.maintenance import MaintenanceDialog

    with tempfile.TemporaryDirectory() as home:
        os.environ["DEVOPS_BUILDER_HOME"] = home
        win.reload_catalog()
        fiche = open_fiche_dialog(win, win.catalog, win.catalog["lsc-keptn"])
        fiche.show()
        app.processEvents()
        fiche.grab().save(str(out / f"12-fiche{suffix}.png"))
        fiche.save()
        win.reload_catalog()
        catalog_edit.write_corrections({"trivy": {"verified": "2025-09-01"}})
        win.reload_catalog()
        p = Project.load(DATA_DIR / "examples" / "02-api-k3s-gitops.devops.yaml")
        p.add("trivy", "security")
        maint = MaintenanceDialog(win.catalog, p, win)
        maint.network.setChecked(False)
        maint.show()
        maint.start()
        wait(lambda: maint.worker is None)
        maint.grab().save(str(out / f"11-entretien{suffix}.png"))
        maint.close()
        del os.environ["DEVOPS_BUILDER_HOME"]
        win.reload_catalog()
    # 13 : ports par environnement, recette et développement sur un même hôte Docker
    from devops_builder.model import env_preset
    from devops_builder.ui.ports import PortsDialog
    p = Project(name="Portail", target="docker-host", environments=env_preset("dev-recette-prod"))
    for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", "docker-compose", "traefik", "prometheus", "grafana"):
        p.add(t, win.catalog[t].stage)
    p.environments[0].host = p.environments[1].host = "vm-hors-prod"
    win._load(p, None)
    ports = PortsDialog(win.project, win.catalog, win, edit_environments=lambda: win.project)
    ports.show()
    app.processEvents()
    ports.grab().save(str(out / f"13-ports{suffix}.png"))
    ports.close()
    # 14 : l'application d'abord — analyse d'un dossier d'exemple
    from devops_builder.ui.application import ApplicationDialog
    with tempfile.TemporaryDirectory() as tmp:
        demo = Path(tmp) / "commandes-api"
        for rel, content in {
            "pyproject.toml": '[project]\nname = "commandes-api"\ndependencies = ["fastapi", "uvicorn"]\n',
            "tests/test_api.py": "def test_ok():\n    assert True\n",
            "Dockerfile": "FROM python:3.12-slim\nEXPOSE 8081\n",
            "charts/commandes/Chart.yaml": "apiVersion: v2\nname: commandes\nversion: 0.1.0\n",
            ".git/config": '[remote "origin"]\n\turl = git@gitlab.example.fr:equipe/commandes-api.git\n',
            "renovate.json": "{}",
        }.items():
            (demo / rel).parent.mkdir(parents=True, exist_ok=True)
            (demo / rel).write_text(content)
        p = Project(name="Commandes", target="kubernetes")
        p.add("gitlab", "source")
        win._load(p, None)
        appdlg = ApplicationDialog(win.project, win.catalog, win)
        appdlg.folder.edit.setText(str(demo))
        appdlg.analyse()
        appdlg.show()
        app.processEvents()
        appdlg.grab().save(str(out / f"14-application{suffix}.png"))
        appdlg.close()
    # 15 : étape Données — base, cache et migrations, brique PostgreSQL sélectionnée
    from devops_builder.model import env_preset
    p = Project(name="Boutique", target="docker-host", environments=env_preset("dev-recette-prod"))
    p.app.image_name = "boutique"
    for t in ("gitlab", "gitlab-ci", "buildkit", "unit-tests", "trivy", "docker-compose", "traefik",
              "postgresql", "valkey", "prometheus", "grafana"):
        p.add(t, win.catalog[t].stage)
    p.add("db-migrations", "data", command="alembic upgrade head")
    win._load(p, None)
    win._focus_brick(p.bricks_for("postgresql")[0].uid)
    app.processEvents()
    win.grab().save(str(out / f"15-donnees{suffix}.png"))
    # 16 : vue « Données » — CloudNativePG sauvegardé, MariaDB en StatefulSet signalée en production
    from devops_builder.ui.data import DataDialog
    p = Project(name="Catalogue produits", target="kubernetes", environments=env_preset("dev-staging-prod"))
    p.app.image_name = "catalogue"
    for t in ("gitlab", "gitlab-ci", "buildkit", "k3s", "helm", "cert-manager", "mongodb", "openbao",
              "external-secrets"):
        p.add(t, win.catalog[t].stage)
    p.add("cloudnative-pg", "data", backup_destination="s3://catalogue-sauvegardes",
          backup_endpoint="https://s3.fr-par.scw.cloud", url_format="jdbc", url_var="SPRING_DATASOURCE_URL")
    win._load(p, None)
    data = DataDialog(win.project, win.catalog, win.engine, win, apply_fix=lambda a: win.project)
    data.show()
    data.tree.setCurrentItem(data.tree.topLevelItem(2))
    app.processEvents()
    data.grab().save(str(out / f"16-vue-donnees{suffix}.png"))
    data.close()
    print("captures écrites dans", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
