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
    print("captures écrites dans", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
