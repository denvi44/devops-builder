# SPDX-License-Identifier: Apache-2.0
"""Produit les icônes (PNG, ICO, ICNS) à partir de packaging/icones/devops-builder.svg.

Usage : QT_QPA_PLATFORM=offscreen python tools/logo.py   (demande Pillow, hors dépendances du projet)
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

RACINE = Path(__file__).resolve().parents[1]
SVG = RACINE / "packaging" / "icones" / "devops-builder.svg"
SORTIE = RACINE / "packaging" / "icones"
DONNEES = RACINE / "devops_builder" / "data" / "logo"


def rendre(taille: int) -> Image.Image:
    rendu = QSvgRenderer(str(SVG))
    image = QImage(taille, taille, QImage.Format.Format_ARGB32)
    image.fill(0)
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    rendu.render(peintre)
    peintre.end()
    octets = QByteArray()
    tampon = QBuffer(octets)
    tampon.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(tampon, "PNG")
    from io import BytesIO
    return Image.open(BytesIO(bytes(octets))).convert("RGBA")


def main() -> int:
    _app = QGuiApplication(sys.argv)
    DONNEES.mkdir(parents=True, exist_ok=True)
    grand = rendre(1024)
    grand.save(SORTIE / "devops-builder-1024.png")
    rendre(256).save(DONNEES / "logo-256.png")
    rendre(64).save(DONNEES / "logo-64.png")
    (DONNEES / "logo.svg").write_text(SVG.read_text(encoding="utf-8"), encoding="utf-8")
    grand.save(SORTIE / "devops-builder.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    grand.save(SORTIE / "devops-builder.icns")
    print("icônes écrites dans", SORTIE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
