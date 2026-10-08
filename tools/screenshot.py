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
    print("captures écrites dans", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
