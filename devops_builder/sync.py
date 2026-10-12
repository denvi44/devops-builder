# SPDX-License-Identifier: Apache-2.0
"""Écriture prudente des fichiers générés dans un dossier ou un dépôt existant.

Un manifeste (`.devops-builder/manifest.json`) garde l'empreinte de chaque fichier
tel que DevOps Builder l'a écrit. À la génération suivante, on sait donc si un
fichier a été retouché à la main depuis : il n'est alors pas écrasé sans accord.
"""

from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

MANIFEST = ".devops-builder/manifest.json"

NEW = "nouveau"
UPDATED = "mis à jour"
SAME = "identique"
EDITED = "modifié à la main"
FOREIGN = "existant"          # fichier présent que DevOps Builder n'a jamais écrit
OBSOLETE = "obsolète"         # écrit autrefois, plus généré aujourd'hui

STATUS_HELP = {
    NEW: "Le fichier n'existe pas encore.",
    UPDATED: "Le fichier vient de DevOps Builder et n'a pas été retouché : il peut être remplacé sans perte.",
    SAME: "Le contenu est déjà à jour.",
    EDITED: "Le fichier a été modifié à la main depuis la dernière génération : le remplacer perdrait ces modifications.",
    FOREIGN: "Un fichier du même nom existe déjà et ne vient pas de DevOps Builder.",
    OBSOLETE: "Généré autrefois, ce fichier ne l'est plus avec le pipeline actuel.",
}
SELECTED_BY_DEFAULT = {NEW, UPDATED}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class FileChange:
    path: str
    status: str
    new: str | None          # None : suppression proposée (obsolète)
    old: str | None
    selected: bool

    @property
    def deletion(self) -> bool:
        return self.new is None

    def diff(self, context: int = 3) -> str:
        if self.status == SAME:
            return ""
        old = (self.old or "").splitlines(keepends=True)
        new = (self.new or "").splitlines(keepends=True)
        lines = difflib.unified_diff(old, new, f"a/{self.path}" if self.old is not None else "/dev/null",
                                     f"b/{self.path}" if self.new is not None else "/dev/null", n=context)
        return "".join(lines)

    def stats(self) -> tuple[int, int]:
        added = removed = 0
        for line in self.diff(0).splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        return added, removed


def read_manifest(root: Path) -> dict[str, str]:
    path = root / MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data.get("files", {}))
    except (OSError, ValueError, AttributeError):
        return {}


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def plan(files: dict[str, str], root: str | Path) -> list[FileChange]:
    """Ce qu'il faudrait faire pour amener `root` au contenu généré, fichier par fichier."""
    root = Path(root)
    manifest = read_manifest(root)
    changes: list[FileChange] = []
    for rel in sorted(files):
        new = files[rel]
        old = _read(root / rel) if (root / rel).is_file() else None
        if old is None:
            status = NEW
        elif old == new:
            status = SAME
        elif rel in manifest:
            status = UPDATED if digest(old) == manifest[rel] else EDITED
        else:
            status = FOREIGN
        changes.append(FileChange(rel, status, new, old, status in SELECTED_BY_DEFAULT))
    for rel in sorted(set(manifest) - set(files)):
        old = _read(root / rel) if (root / rel).is_file() else None
        if old is None:
            continue
        changes.append(FileChange(rel, OBSOLETE, None, old, False))
    return changes


def counts(changes: list[FileChange]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in changes:
        out[c.status] = out.get(c.status, 0) + 1
    return out


def describe(changes: list[FileChange]) -> str:
    c = counts(changes)
    order = [NEW, UPDATED, EDITED, FOREIGN, OBSOLETE, SAME]
    return ", ".join(f"{c[s]} {s}" for s in order if c.get(s))


def apply(changes: list[FileChange], root: str | Path) -> list[str]:
    """Écrit (ou supprime) les fichiers sélectionnés et met le manifeste à jour.

    Le manifeste retient l'empreinte de ce qui a été écrit ; un fichier laissé de côté garde
    l'ancienne empreinte, si bien qu'il reste signalé comme retouché à la génération suivante.
    """
    root = Path(root)
    manifest = read_manifest(root)
    touched: list[str] = []
    for ch in changes:
        path = root / ch.path
        if ch.status == SAME:
            manifest[ch.path] = digest(ch.new or "")
            continue
        if not ch.selected:
            continue
        if ch.deletion:
            path.unlink(missing_ok=True)
            manifest.pop(ch.path, None)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(ch.new or "", encoding="utf-8")
            if ch.path.endswith(".sh"):
                path.chmod(0o755)
            manifest[ch.path] = digest(ch.new or "")
        touched.append(ch.path)
    mpath = root / MANIFEST
    mpath.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"generator": "devops-builder", "files": dict(sorted(manifest.items()))}, indent=2,
                      ensure_ascii=False) + "\n"
    if _read(mpath) != text:
        mpath.write_text(text, encoding="utf-8")
        touched.append(MANIFEST)
    return touched
