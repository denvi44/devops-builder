# SPDX-License-Identifier: Apache-2.0
"""Le logo est présent pour chaque cible de paquet et chargé par l'application."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_fichiers_du_logo():
    icones = ROOT / "packaging" / "icones"
    assert (icones / "devops-builder.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"
    assert (icones / "devops-builder.icns").read_bytes()[:4] == b"icns"
    assert (icones / "devops-builder-1024.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (ROOT / "docs" / "assets" / "logo.png").exists() and (ROOT / "packaging" / "devops-builder.desktop").exists()


def test_cibles_de_paquet_referencent_le_logo():
    spec = (ROOT / "packaging" / "devops-builder.spec").read_text(encoding="utf-8")
    assert "icones/devops-builder.ico" in spec and "icones/devops-builder.icns" in spec
    flow = (ROOT / ".github" / "workflows" / "publication.yml").read_text(encoding="utf-8")
    assert "devops-builder.desktop" in flow and "devops-builder.png" in flow


def test_icone_de_l_application():
    from PySide6.QtWidgets import QApplication

    from devops_builder.ui.app import app_icon
    QApplication.instance() or QApplication([])
    assert not app_icon().isNull()
