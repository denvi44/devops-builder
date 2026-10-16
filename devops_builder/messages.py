# SPDX-License-Identifier: Apache-2.0
"""Erreurs du système traduites pour l'utilisateur : ce qui s'est passé, sur quoi, et quoi faire.

Les messages de Python (« [Errno 13] Permission denied »), de PyYAML (« mapping values are not allowed
here ») ou d'une commande lancée (git, tofu…) arrivent en anglais et sans conseil ; ils ne doivent pas
atteindre l'interface ni la ligne de commande tels quels.
"""

from __future__ import annotations

import errno
import subprocess
from pathlib import Path

_OS = {
    errno.ENOENT: "n'existe pas",
    errno.EACCES: "accès refusé (droits du fichier ou du dossier)",
    errno.EPERM: "opération refusée par le système (droits insuffisants)",
    errno.EISDIR: "c'est un dossier, un fichier était attendu",
    errno.ENOTDIR: "un élément du chemin n'est pas un dossier",
    errno.ENOSPC: "plus de place sur le disque",
    errno.EROFS: "le disque est en lecture seule",
    errno.EEXIST: "existe déjà",
    errno.ENAMETOOLONG: "nom de fichier trop long",
    errno.EBUSY: "fichier occupé par un autre programme",
    errno.ENOTEMPTY: "le dossier n'est pas vide",
    errno.EXDEV: "déplacement impossible entre deux disques",
    errno.ETIMEDOUT: "délai de connexion dépassé",
    errno.ECONNREFUSED: "connexion refusée (service arrêté ou mauvais port ?)",
    errno.EHOSTUNREACH: "machine injoignable (réseau ou pare-feu)",
    errno.ENETUNREACH: "réseau injoignable (connexion à internet ?)",
}

# Problèmes signalés par PyYAML → explication et piste de correction
_YAML = [
    ("found character '\\t' that cannot start any token", "tabulation interdite en YAML : indenter avec des espaces"),
    ("mapping values are not allowed here",
     "« : » inattendu : mettre la valeur entre guillemets, ou revoir l'indentation de la ligne"),
    ("could not find expected ':'", "« : » manquant après une clé, ou indentation incohérente"),
    ("expected <block end>", "indentation incohérente avec les lignes précédentes"),
    ("expected the node content, but found '<stream end>'",
     "le fichier s'arrête au milieu d'une valeur : crochet [ ou accolade { non fermé ?"),
    ("found unexpected end of stream", "guillemet non fermé"),
    ("expected ',' or ']'", "liste entre crochets mal fermée : « , » ou « ] » attendu"),
    ("expected ',' or '}'", "dictionnaire entre accolades mal fermé : « , » ou « } » attendu"),
    ("found undefined alias", "alias YAML (*nom) sans ancre (&nom) correspondante"),
    ("found duplicate anchor", "ancre YAML (&nom) définie deux fois"),
    ("found unknown escape character", "séquence d'échappement inconnue dans une chaîne entre guillemets doubles"),
    ("did not find expected key", "clé attendue : indentation incohérente, ou tiret de liste mal placé"),
    ("did not find expected '-' indicator", "élément de liste attendu (« - ») à cette indentation"),
    ("found character that cannot start any token", "caractère interdit en début de valeur : mettre la valeur entre guillemets"),
]


def yaml_problem(exc: BaseException) -> str:
    """« YAML invalide ligne 3, colonne 5 : explication » pour une erreur de PyYAML."""
    problem = str(getattr(exc, "problem", "") or exc)
    mark = getattr(exc, "problem_mark", None)
    where = f" ligne {mark.line + 1}, colonne {mark.column + 1}" if mark else ""
    for needle, text in _YAML:
        if needle in problem:
            return f"YAML invalide{where} : {text}"
    return f"YAML invalide{where} (analyseur : {problem.strip()})"


def explain(exc: BaseException, subject: str | Path | None = None) -> str:
    """Message en français pour une erreur, sans trace Python ; subject : le fichier ou la ressource visés."""
    import yaml

    what = f"« {subject} » : " if subject else ""
    if isinstance(exc, UnicodeDecodeError):
        return f"{what}n'est pas un fichier texte UTF-8 (octet {exc.object[exc.start]:#04x} en position {exc.start})"
    if isinstance(exc, yaml.YAMLError):
        return f"{what}{yaml_problem(exc)}"
    if isinstance(exc, subprocess.TimeoutExpired):
        cmd = exc.cmd if isinstance(exc.cmd, str) else " ".join(map(str, exc.cmd[:3]))
        return f"la commande « {cmd} » n'a pas répondu en {int(exc.timeout)} s"
    if isinstance(exc, subprocess.CalledProcessError):
        cmd = exc.cmd if isinstance(exc.cmd, str) else " ".join(map(str, exc.cmd[:3]))
        out = (exc.stderr or exc.output or "")
        out = out.decode(errors="replace") if isinstance(out, bytes) else out
        last = next((line.strip() for line in reversed(out.splitlines()) if line.strip()), "")
        return f"la commande « {cmd} » a échoué (code {exc.returncode})" + (f" : {last}" if last else "")
    if isinstance(exc, FileNotFoundError) and exc.filename and not subject and Path(str(exc.filename)).name in (
            "git", "tofu", "terraform", "helm", "kubectl", "kind", "docker"):
        return f"programme « {exc.filename} » introuvable : l'installer, ou l'ajouter au PATH"
    if isinstance(exc, OSError):
        target = subject or exc.filename
        why = _OS.get(exc.errno or -1, exc.strerror or str(exc))
        return f"« {target} » : {why}" if target else why[:1].upper() + why[1:]
    text = str(exc).strip()
    return f"{what}{text}" if text else f"{what}erreur inattendue ({type(exc).__name__})"


def reason(exc: BaseException) -> str:
    """La cause seule, quand le message qui l'entoure nomme déjà le fichier."""
    if isinstance(exc, OSError) and not isinstance(exc, subprocess.SubprocessError):
        return _OS.get(exc.errno or -1, exc.strerror or str(exc))
    return explain(exc)
