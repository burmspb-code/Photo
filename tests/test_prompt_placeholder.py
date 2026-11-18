"""Промпт — подсказка при старте, а не текст прошлой генерации."""
from __future__ import annotations

from src.ui.defaults import PROMPT_PLACEHOLDER, apply_default_presets
from src.ui.main_window import MainWindow
from src.ui.settings_dialog import SettingsDialog
from tests.gui_case import GuiTestCase, app_settings


class TestPromptPlaceholder(GuiTestCase):
    def setUp(self) -> None:
        stored = app_settings()
        stored.clear()
        stored.setValue("bg/prompt", "realistic photo, old generation")
        stored.sync()

    def test_main_window_starts_empty_with_placeholder(self) -> None:
        apply_default_presets(app_settings())
        window = MainWindow()
        try:
            self.assertEqual(window.prompt.toPlainText(), "")
            self.assertEqual(window.prompt.placeholderText(), PROMPT_PLACEHOLDER)
            self.assertEqual(window.current_params()["prompt"], "")
            self.assertIsNone(app_settings().value("bg/prompt"))
        finally:
            window.close()
            window.deleteLater()
            self.process_events()

    def test_typed_text_is_not_the_placeholder(self) -> None:
        window = MainWindow()
        try:
            window.prompt.setPlainText("realistic photo, snowy forest")
            self.assertEqual(window.prompt.toPlainText(), "realistic photo, snowy forest")
            self.assertEqual(window.current_params()["prompt"], "realistic photo, snowy forest")
            self.assertEqual(window.prompt.placeholderText(), PROMPT_PLACEHOLDER)
        finally:
            window.close()
            window.deleteLater()
            self.process_events()

    def test_settings_dialog_never_restores_or_saves_prompt(self) -> None:
        dialog = SettingsDialog()
        try:
            field = dialog.controls["bg/prompt"]
            self.assertEqual(field.toPlainText(), "")
            self.assertEqual(field.placeholderText(), PROMPT_PLACEHOLDER)
            self.assertEqual(dialog.prompt_text, "")

            field.setPlainText("  realistic photo, arctic shore  ")
            self.assertEqual(dialog.prompt_text, "realistic photo, arctic shore")
            dialog._save()
            self.assertIsNone(app_settings().value("bg/prompt"))
        finally:
            dialog.close()
            dialog.deleteLater()
            self.process_events()

    def test_migration_drops_legacy_prompt_without_other_changes(self) -> None:
        stored = app_settings()
        stored.setValue("app/defaults_version", 1)
        stored.setValue("cut/model", "birefnet-portrait")
        stored.sync()

        self.assertFalse(apply_default_presets(stored))

        self.assertIsNone(stored.value("bg/prompt"))
        self.assertEqual(stored.value("cut/model"), "birefnet-portrait")
