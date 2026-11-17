"""Общая настройка Qt для GUI-тестов.

QSettings перенаправляются во временную папку, чтобы тесты не меняли
настройки реального приложения. В этой сборке PyQt6 setDefaultFormat()
не влияет на QSettings("Photo", "Photo"), поэтому экземпляр создаётся
явно с форматом IniFormat и подменяется в модулях GUI.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication


def app_settings() -> QSettings:
    """Изолированный экземпляр QSettings приложения."""
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "Photo", "Photo")


def _isolated_settings(*args, **kwargs) -> QSettings:
    return app_settings()


class GuiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls._settings_dir = tempfile.TemporaryDirectory(prefix="photo-tests-")
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            cls._settings_dir.name,
        )
        for module in ("src.ui.main_window", "src.ui.settings_dialog"):
            patcher = patch(f"{module}.QSettings", new=_isolated_settings)
            patcher.start()
            cls.addClassCleanup(patcher.stop)

    @classmethod
    def tearDownClass(cls) -> None:
        app_settings().sync()
        cls._settings_dir.cleanup()

    @staticmethod
    def process_events() -> None:
        QApplication.processEvents()
