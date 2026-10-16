# SPDX-License-Identifier: Apache-2.0
"""Audit d'accessibilité automatisé de l'interface, dans les deux thèmes.

    python tools/audit_accessibilite.py [--sans-focus]

Ouvre la fenêtre principale sur un exemple puis chaque dialogue, hors écran, et liste les constats
(nom accessible, clavier, focus visible, contrastes, titres, langue, raccourcis, texte coupé à 200 %). Code de sortie 1 s'il y en a.
"""

from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DEVOPS_BUILDER_HOME", tempfile.mkdtemp(prefix="audit-a11y-"))


def main() -> int:
    from devops_builder.catalog import DATA_DIR
    from devops_builder.ui.app import create_window
    from devops_builder.ui.audit import CRITERIA, clipped_at, full_audit
    app, win = create_window(["devops-builder"])
    win.show()
    win.activateWindow()
    win.open_path(DATA_DIR / "examples" / "01-web-hote-docker.devops.yaml")
    app.processEvents()
    total = 0
    for dark in (False, True):
        if win.dark != dark:
            win.toggle_theme()
            app.processEvents()
        findings = full_audit(win, focus="--sans-focus" not in sys.argv) + clipped_at(win, 2.0)
        print(f"== thème {'sombre' if dark else 'clair'} : {len(findings)} constat(s)")
        for f in findings:
            en, wcag, rgaa = CRITERIA[f.criterion]
            print(f"  {f}   ({wcag} ; EN 301 549 {en} ; {rgaa})")
        total += len(findings)
    win.undo_stack.setClean()
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
