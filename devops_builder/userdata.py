"""Emplacements des données de l'utilisateur (catalogue personnel, index du Landscape, caches).

DEVOPS_BUILDER_HOME change le dossier de base : utile pour partager un catalogue d'équipe
versionné dans Git, ou pour isoler les tests.
"""

from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("DEVOPS_BUILDER_HOME") or Path.home() / ".devops-builder")


def catalog_dir() -> Path:
    """Fiches personnelles (fiches/*.yaml) et corrections de fiches livrées (corrections.yaml)."""
    return home() / "catalog"


def user_fiches_dir() -> Path:
    return catalog_dir() / "fiches"


def corrections_file() -> Path:
    return catalog_dir() / "corrections.yaml"


def landscape_index() -> Path:
    """Index du Landscape rafraîchi par l'utilisateur ; prioritaire sur celui livré."""
    return home() / "landscape_index.json"


def cache_dir() -> Path:
    return home() / "cache"
