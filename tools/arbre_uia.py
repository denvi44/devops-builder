# SPDX-License-Identifier: Apache-2.0
"""Arbre d'accessibilité de l'interface tel que le lisent NVDA et le Narrateur (UI Automation, Windows).

    python tools/arbre_uia.py [--sortie arbre.txt]

Lance l'application sur un exemple, lit l'arbre UI Automation de sa fenêtre, puis du dialogue des
paramètres du projet ouvert par le bouton du même nom. Mêmes règles que tools/arbre_accessibilite.py
(AT-SPI) : un élément atteignable au clavier a un nom, aucun texte de Qt n'est resté en anglais.
Demande le paquet Python « uiautomation » (pip install uiautomation).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arbre_accessibilite import EXAMPLE, ROOT, problems, render  # noqa: E402

ROLES = {"ButtonControl": "push button", "EditControl": "text", "ComboBoxControl": "combo box",
         "CheckBoxControl": "check box", "RadioButtonControl": "radio button", "ListControl": "list",
         "ListItemControl": "list item", "TreeControl": "tree", "TreeItemControl": "tree item",
         "TabControl": "page tab list", "TabItemControl": "page tab", "DataItemControl": "table cell",
         "PaneControl": "filler", "GroupControl": "panel", "TextControl": "label", "SpinnerControl": "spin button",
         "ScrollBarControl": "scroll bar", "MenuBarControl": "menu bar", "MenuItemControl": "menu item",
         "ToolBarControl": "tool bar", "StatusBarControl": "status bar", "WindowControl": "frame",
         "ImageControl": "image", "HeaderControl": "table column header", "HeaderItemControl": "table column header"}


def dump(control, depth=0, out=None, limit=600):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    try:
        if control.ControlTypeName == "TitleBarControl":
            return out  # barre de titre dessinée par Windows (boutons dans la langue du système), pas par l'application
        role = ROLES.get(control.ControlTypeName, control.ControlTypeName)
        out.append({"depth": depth, "role": role, "name": control.Name or "",
                    "description": getattr(control, "HelpText", "") or "",
                    "focusable": bool(control.IsKeyboardFocusable), "showing": not control.IsOffscreen})
        children = control.GetChildren()
    except Exception:  # noqa: BLE001 (élément disparu pendant la lecture)
        return out
    for child in children:
        dump(child, depth + 1, out, limit)
    return out


def main() -> int:
    import uiautomation as auto  # noqa: PLC0415 (Windows seulement)

    out = Path(sys.argv[sys.argv.index("--sortie") + 1]) if "--sortie" in sys.argv else None
    home = tempfile.mkdtemp(prefix="arbre-uia-")
    env = {**os.environ, "DEVOPS_BUILDER_HOME": home, "QT_ACCESSIBILITY": "1"}
    app = subprocess.Popen([sys.executable, "-m", "devops_builder", str(EXAMPLE)], env=env, cwd=ROOT)
    windows: dict[str, list[dict]] = {}
    try:
        win = auto.WindowControl(searchDepth=1, SubName="DevOps Builder")
        if not win.Exists(maxSearchSeconds=40):
            print("fenêtre de l'application introuvable par UI Automation", file=sys.stderr)
            return 2
        time.sleep(3)
        windows["principale"] = dump(win)
        button = win.ButtonControl(Name="Paramètres du projet")
        if button.Exists(maxSearchSeconds=5):
            button.GetInvokePattern().Invoke()
            dialog = auto.WindowControl(searchDepth=2, SubName="Paramètres du projet")
            if dialog.Exists(maxSearchSeconds=10):
                time.sleep(1)
                windows["paramètres"] = dump(dialog)
    finally:
        app.terminate()
    text = render(windows)
    if out:
        out.write_text(text, encoding="utf-8")
    else:
        print(text)
    found = problems(windows)
    for f in found:
        print(f"::error::{f}" if os.environ.get("GITHUB_ACTIONS") else f"✗ {f}")
    counts = {k: sum(1 for r in v if r["showing"]) for k, v in windows.items()}
    print(f"{', '.join(f'{k} : {n} éléments' for k, n in counts.items())} ; {len(found)} problème(s)")
    if "paramètres" not in windows:
        print("le dialogue des paramètres ne s'est pas ouvert par UI Automation", file=sys.stderr)
        return 1
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
