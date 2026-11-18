"""Тесты пункта меню «О программе» и содержимого одноимённого диалога."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QScrollArea

from src.ui.about_dialog import AboutDialog
from src.ui.main_window import MainWindow
from src.ui.settings_dialog import SettingsDialog
from src.ui.styles import THEMES
from tests.gui_case import GuiTestCase


class TestAboutDialog(GuiTestCase):
    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.process_events()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.process_events()

    def test_about_action_is_top_level_in_menu_bar(self) -> None:
        titles = [action.text().replace("&", "") for action in self.window.menuBar().actions()]
        self.assertIn("О программе", titles)
        self.assertEqual(self.window.act_about.text(), "&О программе")

    def test_open_about_shows_dialog(self) -> None:
        with patch.object(AboutDialog, "exec", return_value=QDialog.DialogCode.Rejected) as show:
            self.window.open_about()
        show.assert_called_once()

    def test_about_describes_purpose_steps_and_tools(self) -> None:
        dialog = AboutDialog(self.window)
        texts = {label.objectName(): label.text() for label in dialog.findChildren(QLabel)}

        self.assertIn("замена фона", texts["aboutTitle"])
        self.assertIn("оставить на фото", texts["aboutPurpose"])
        for phrase in ("Вырезать объект", "Сгенерировать фон", "Собрать композит"):
            self.assertIn(phrase, texts["aboutSteps"])
        for tool in ("BiRefNet", "rembg", "pymatting", "FLUX 1 schnell", "Cloudflare",
                     "Real-ESRGAN", "OpenCV", "PyQt6", "по-русски"):
            self.assertIn(tool, texts["aboutTools"])
        self.assertIn("не отправляется в интернет", texts["aboutPrivacy"])

    def test_about_explains_market_and_advantages(self) -> None:
        dialog = AboutDialog(self.window)
        market = dialog.findChild(QLabel, "aboutMarket").text()
        for name in ("remove.bg", "Adobe Express", "Canva", "Photoroom", "Pixelcut", "Photoshop"):
            self.assertIn(name, market)
        for phrase in ("подписк", "водяных знаков", "Русский запрос", "в одном окне"):
            self.assertIn(phrase, market)

    def test_about_resolution_is_limited_by_model(self) -> None:
        dialog = AboutDialog(self.window)
        resolution = dialog.findChild(QLabel, "aboutResolution").text()
        for phrase in ("1024×768", "2048×1536", "4096×3072", "1024×1024",
                       "увеличивает", "ограничено возможностями подключённой модели"):
            self.assertIn(phrase, resolution)
        tools = dialog.findChild(QLabel, "aboutTools").text()
        self.assertNotIn("Готовый фон сохраняется", tools)

    def test_about_content_background_follows_theme(self) -> None:
        # QSS задаёт фон через objectName; без него вьюпорт остаётся системным
        # светлым и светлый текст в тёмной теме становится нечитаемым.
        dialog = AboutDialog(self.window)
        viewport = dialog.findChild(QScrollArea).viewport()
        self.assertEqual(viewport.objectName(), "aboutViewport")
        for theme in THEMES:
            with self.subTest(theme=theme):
                self.assertIn(f"QWidget#{viewport.objectName()}", THEMES[theme])

    def test_native_titlebar_follows_theme(self) -> None:
        self.assertEqual(self.window._theme_name, "Тёмная")
        with patch("src.ui.about_dialog.apply_dark_titlebar") as about_dwm, \
             patch("src.ui.settings_dialog.apply_dark_titlebar") as settings_dwm:
            about = AboutDialog(self.window)
            about.showEvent(QShowEvent())
            about_dwm.assert_called_once_with(about, True)

            self.window._apply_theme("Светлая")
            light_about = AboutDialog(self.window)
            light_about.showEvent(QShowEvent())
            about_dwm.assert_called_with(light_about, False)

            settings = SettingsDialog(self.window)
            settings.showEvent(QShowEvent())
            settings_dwm.assert_called_once_with(settings, False)

        self.window._apply_theme("Тёмная")

    def test_about_dialog_has_close_button(self) -> None:
        dialog = AboutDialog(self.window)
        buttons = dialog.findChild(QDialogButtonBox)
        self.assertIsNotNone(buttons)
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        self.assertIsNotNone(close)
        self.assertTrue(close.isEnabled())


if __name__ == "__main__":
    unittest.main()
