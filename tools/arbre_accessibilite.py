# SPDX-License-Identifier: Apache-2.0
"""Arbre d'accessibilité de l'interface tel que le lit Orca (AT-SPI, Linux).

    python tools/arbre_accessibilite.py [--sortie arbre.txt]

Lance l'application sur un exemple, avec le pont d'accessibilité de Qt, dans un écran virtuel (Xvfb) si
aucun n'est ouvert, puis lit l'arbre par AT-SPI, comme un lecteur d'écran : fenêtre principale, puis le
dialogue des paramètres du projet ouvert par l'action « Paramètres du projet ». Échoue si un élément
atteignable au clavier n'a pas de nom, ou si un texte de Qt est resté en anglais.

Demande Xvfb, dbus, at-spi2-core et python3-pyatspi (paquets Debian et Ubuntu) ; le client AT-SPI tourne
avec le Python du système (/usr/bin/python3), celui de python3-gi.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "devops_builder/data/examples/01-web-hote-docker.devops.yaml"
ENGLISH = re.compile(r"^(OK|Cancel|Close|Float|Apply|Yes|No|Save|Discard|Help|Next|Back|Finish|Undo|Redo)$|"
                     r"dock widget")


# ------------------------------------------------------------------ côté client (Python du système)
def _client() -> int:
    import pyatspi  # noqa: PLC0415 (absent du Python de l'application)

    def find_app():
        for _ in range(40):
            for a in pyatspi.Registry.getDesktop(0):
                if a is not None and "devops" in (a.name or "").lower():
                    return a
            time.sleep(0.5)
        return None

    def dump(node, depth=0, out=None):
        out = [] if out is None else out
        try:
            st = node.getState()
            row = {"depth": depth, "role": node.getRoleName(), "name": node.name or "",
                   "description": node.description or "", "focusable": st.contains(pyatspi.STATE_FOCUSABLE),
                   "showing": st.contains(pyatspi.STATE_SHOWING)}
        except Exception:  # noqa: BLE001 (nœud disparu pendant la lecture)
            return out
        out.append(row)
        for i in range(min(node.childCount, 300)):
            try:
                dump(node.getChildAtIndex(i), depth + 1, out)
            except Exception:  # noqa: BLE001
                pass
        return out

    def press(node, name, role="push button") -> bool:
        try:
            if node.getRoleName() == role and node.name == name:
                action = node.queryAction()
                for i in range(action.nActions):
                    if action.getName(i) in ("Press", "press", "click", "SetFocus") or i == 0:
                        action.doAction(i)
                        return True
        except Exception:  # noqa: BLE001
            pass
        for i in range(node.childCount):
            try:
                if press(node.getChildAtIndex(i), name, role):
                    return True
            except Exception:  # noqa: BLE001
                pass
        return False

    app = find_app()
    if app is None:
        print(json.dumps({"error": "application introuvable sur le bus AT-SPI"}))
        return 1
    windows = {"principale": dump(app)}
    if press(app, "Paramètres du projet"):
        time.sleep(2)
        frames = [app.getChildAtIndex(i) for i in range(app.childCount)]
        dialog = next((f for f in frames if f is not None and f.getRoleName() in ("dialog", "frame")
                       and "Paramètres" in (f.name or "")), None)
        if dialog is not None:
            windows["paramètres"] = dump(dialog)
    print(json.dumps(windows, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------ côté lanceur
def problems(windows: dict[str, list[dict]]) -> list[str]:
    found = []
    for label, rows in windows.items():
        for r in rows:
            if not r["showing"]:
                continue
            if r["focusable"] and not r["name"].strip() and r["role"] not in ("table cell",):
                found.append(f"{label} : {r['role']} atteignable au clavier sans nom")
            for text in (r["name"], r["description"]):
                if text and ENGLISH.search(text):
                    found.append(f"{label} : texte en anglais « {text} » ({r['role']})")
    return found


def render(windows: dict[str, list[dict]]) -> str:
    lines = []
    for label, rows in windows.items():
        lines.append(f"## Fenêtre {label}")
        for r in rows:
            if r["showing"] or r["depth"] < 2:
                desc = f" — {r['description']!r}" if r["description"] else ""
                lines.append("  " * r["depth"] + f"[{r['role']}] {r['name']!r}{desc}" + (" ⌨" if r["focusable"] else ""))
    return "\n".join(lines) + "\n"


def _system_python() -> str:
    """Un Python du système qui importe pyatspi (python3-gi n'est construit que pour la version de la distribution)."""
    for name in ("python3", "python3.13", "python3.12", "python3.11", "python3.10"):
        exe = shutil.which(name, path="/usr/bin")
        if exe and subprocess.run([exe, "-c", "import pyatspi"], capture_output=True).returncode == 0:
            return exe
    raise SystemExit(_fail("pyatspi introuvable : installer python3-pyatspi (paquet du système)"))


def _fail(message: str, code: int = 2) -> int:
    print(f"::error::{message}" if os.environ.get("GITHUB_ACTIONS") else message, file=sys.stderr)
    return code


def main() -> int:
    if "--client" in sys.argv:
        return _client()
    out = Path(sys.argv[sys.argv.index("--sortie") + 1]) if "--sortie" in sys.argv else None
    procs: list[subprocess.Popen] = []
    env = {**os.environ}
    try:
        if not env.get("DISPLAY"):
            env["DISPLAY"] = ":97"
            procs.append(subprocess.Popen(["Xvfb", ":97", "-screen", "0", "1600x1000x24"],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            time.sleep(1)
        bus = subprocess.run(["dbus-launch", "--sh-syntax"], capture_output=True, text=True, check=True).stdout
        for key, value in re.findall(r"(DBUS_SESSION_BUS_ADDRESS|DBUS_SESSION_BUS_PID)='?([^';]+)'?;", bus):
            env[key] = value
        launcher = next((p for p in ("/usr/libexec/at-spi-bus-launcher", "/usr/lib/at-spi2-core/at-spi-bus-launcher")
                         if Path(p).exists()), None)
        if launcher:
            procs.append(subprocess.Popen([launcher, "--launch-immediately"], env=env,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            time.sleep(1)
        home = tempfile.mkdtemp(prefix="arbre-a11y-")
        app_env = {**env, "QT_QPA_PLATFORM": "xcb", "QT_ACCESSIBILITY": "1", "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1",
                   "HOME": home, "DEVOPS_BUILDER_HOME": home}
        procs.append(subprocess.Popen([sys.executable, "-m", "devops_builder", str(EXAMPLE)], env=app_env, cwd=ROOT,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        time.sleep(6)
        system_python = _system_python()
        r = subprocess.run([system_python, __file__, "--client"], env=env, capture_output=True, text=True, timeout=180)
        try:
            windows = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return _fail(f"client AT-SPI sans résultat : {(r.stdout + r.stderr)[-1500:]}".replace("\n", " | "))
        if "error" in windows:
            return _fail(windows["error"])
    finally:
        for p in reversed(procs):
            p.terminate()
        if env.get("DBUS_SESSION_BUS_PID"):
            subprocess.run(["kill", env["DBUS_SESSION_BUS_PID"]], check=False)
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
        return _fail("le dialogue des paramètres ne s'est pas ouvert par AT-SPI", 1)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
