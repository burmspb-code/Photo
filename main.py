"""Точка входа GUI: python main.py из корня проекта."""
from __future__ import annotations

import sys

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from src.ui.defaults import apply_default_presets
from src.ui.main_window import MainWindow


def main() -> None:
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    app = QApplication(sys.argv)
    app.setApplicationName("Photo")
    app.setOrganizationName("Photo")

    # Приводим устаревшие ключи к значениям, с которыми был получен результат C.
    apply_default_presets(QSettings("Photo", "Photo"))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
