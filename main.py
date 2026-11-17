"""Точка входа GUI: python main.py из корня проекта."""
from __future__ import annotations

import sys

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def main() -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    app = QApplication(sys.argv)
    app.setApplicationName("Photo")
    app.setOrganizationName("Photo")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
