# SPDX-License-Identifier: Apache-2.0
"""Compare deux séries de captures (non-régression visuelle) : part de pixels différents.

    QT_QPA_PLATFORM=offscreen python tools/compare_captures.py reference/ nouvelles/ [--seuil 2]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QImage


def difference(a: Path, b: Path, tolerance: int = 24) -> float | None:
    ia, ib = QImage(str(a)), QImage(str(b))
    if ia.size() != ib.size():
        return None
    ia = ia.convertToFormat(QImage.Format.Format_RGB32)
    ib = ib.convertToFormat(QImage.Format.Format_RGB32)
    w, h = ia.width(), ia.height()
    step = 2  # un pixel sur quatre suffit pour repérer un écart
    diff = total = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            pa, pb = ia.pixelColor(x, y), ib.pixelColor(x, y)
            total += 1
            if abs(pa.red() - pb.red()) + abs(pa.green() - pb.green()) + abs(pa.blue() - pb.blue()) > tolerance:
                diff += 1
    return 100.0 * diff / max(total, 1)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    _app = QGuiApplication(sys.argv[:1])
    ref, new = Path(sys.argv[1]), Path(sys.argv[2])
    threshold = float(sys.argv[sys.argv.index("--seuil") + 1]) if "--seuil" in sys.argv else 2.0
    worst = 0
    for a in sorted(ref.glob("*.png")):
        b = new / a.name
        if not b.exists():
            print(f"  absente      {a.name}")
            worst = 1
            continue
        d = difference(a, b)
        if d is None:
            print(f"  taille ≠     {a.name}")
            worst = 1
        else:
            flag = "ÉCART" if d > threshold else "ok"
            print(f"  {flag:5} {d:5.1f} %  {a.name}")
            worst = max(worst, int(d > threshold))
    for b in sorted(set(p.name for p in new.glob("*.png")) - set(p.name for p in ref.glob("*.png"))):
        print(f"  nouvelle     {b}")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
