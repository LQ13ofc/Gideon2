#!/usr/bin/env python3
"""Render SVG mockups to PNG with Qt (no browser needed).

Usage: target/ui-venv/bin/python -I -B scripts/render_svg.py in.svg [out.png] [width height]
Default size 1380x904. Runs offscreen; fonts come from the system (Noto Sans).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src = argv[1]
    out = argv[2] if len(argv) > 2 else os.path.splitext(src)[0] + ".png"
    width = int(argv[3]) if len(argv) > 3 else 1380
    height = int(argv[4]) if len(argv) > 4 else 904
    app = QGuiApplication([])
    renderer = QSvgRenderer(src)
    if not renderer.isValid():
        print("invalid svg:", src)
        return 1
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    renderer.render(painter)
    painter.end()
    image.save(out)
    print("wrote", out)
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
