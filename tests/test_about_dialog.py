"""Тесты пункта меню «О программе» и содержимого одноимённого диалога."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTabWidget, QWidget

from src.ui.about_dialog import HELP_GROUPS, AboutDialog, _default_text, _render_help
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
        # В диалоге два QScrollArea; ищем вьюпорт именно вкладки «О приложении».
        viewport = dialog.findChild(QWidget, "aboutContent").parentWidget()
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

    def test_about_has_app_and_help_tabs(self) -> None:
        dialog = AboutDialog(self.window)
        tabs = dialog.findChild(QTabWidget)
        self.assertIsNotNone(tabs)
        self.assertEqual(tabs.count(), 2)
        self.assertEqual(tabs.tabText(0), "О приложении")
        self.assertEqual(tabs.tabText(1), "Помощь")
        self.assertIsNotNone(dialog.findChild(QLabel, "aboutTitle"))
        self.assertIsNotNone(dialog.findChild(QLabel, "helpText"))

    def test_help_covers_every_settings_control(self) -> None:
        """В справке должен быть описан каждый параметр из окна «Настройки»."""
        help_keys = {
            key
            for _tab, sections in HELP_GROUPS
            for _section_title, settings in sections
            for key, _label, _description in settings
        }
        settings = SettingsDialog(self.window)
        control_keys = set(settings.controls)
        self.assertTrue(control_keys <= help_keys, f"нет справки для: {sorted(control_keys - help_keys)}")
        self.assertEqual(help_keys, control_keys)

    def test_help_group_titles_match_settings_tabs(self) -> None:
        """Справка сгруппирована по тем же вкладкам, что и диалог настроек."""
        tabs = SettingsDialog(self.window).findChild(QTabWidget)
        ui_titles = tuple(tabs.tabText(i) for i in range(tabs.count()))
        self.assertEqual(tuple(group[0] for group in HELP_GROUPS), ui_titles)

    def test_help_text_has_descriptions_defaults_and_scenarios(self) -> None:
        dialog = AboutDialog(self.window)
        help_text = dialog.findChild(QLabel, "helpText").text()
        for phrase in (
            "на что",
            "по умолчанию",
            "birefnet-general",
            "u2netp",
            "Портретный режим",
            "Контактная тень",
            "когда",
        ):
            self.assertIn(phrase, help_text)
        self.assertIn("по умолчанию: вкл.", help_text)
        self.assertIn("по умолчанию: ×2", help_text)
        self.assertIn("Сбросить настройки", help_text)
        self.assertIn("OK", help_text)

    def test_help_defaults_follow_presets(self) -> None:
        """Строка «по умолчанию» берётся из APP_DEFAULTS, а не захардкожена."""
        self.assertEqual(_default_text("cut/portrait"), "вкл.")
        self.assertEqual(_default_text("compose/blur"), "0.5")
        self.assertEqual(_default_text("upscale/factor"), "×2")
        self.assertEqual(_default_text("bg/prompt"), "не сохраняется")
        self.assertIn("по умолчанию: 0.5", _render_help())

    def test_help_background_follows_theme(self) -> None:
        dialog = AboutDialog(self.window)
        help_content = dialog.findChild(QLabel, "helpText").parentWidget()
        self.assertEqual(help_content.objectName(), "helpContent")
        for theme in THEMES:
            with self.subTest(theme=theme):
                self.assertIn("QWidget#helpContent", THEMES[theme])


if __name__ == "__main__":
    unittest.main()
