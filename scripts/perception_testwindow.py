#!/usr/bin/env python3
"""Test window opened by scripts/perception_live.py: one labelled line edit, closed after N seconds.

Usage: target/ui-venv/bin/python scripts/perception_testwindow.py <seconds>
It exposes its widgets through AT-SPI (QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 is set by the caller)."""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    app = QApplication(sys.argv[:1])
    win = QWidget()
    win.setWindowTitle("Gideon perception test window")
    layout = QVBoxLayout(win)
    layout.addWidget(QLabel("Janela de teste do Gideon (criada pelo teste de percepção)"))
    edit = QLineEdit()
    edit.setAccessibleName("campo de teste")
    layout.addWidget(edit)
    win.resize(520, 160)
    win.show()
    edit.setFocus()
    QTimer.singleShot(seconds * 1000, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
