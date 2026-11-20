"""Предустановки: регресс вырезки и однократная миграция QSettings."""
from __future__ import annotations

from src.ui.defaults import APP_DEFAULTS, DEFAULTS_VERSION, apply_default_presets
from src.ui.main_window import MainWindow
from src.ui.settings_dialog import SettingsDialog
from tests.gui_case import GuiTestCase, app_settings


class TestDefaults(GuiTestCase):
    def setUp(self) -> None:
        stored = app_settings()
        stored.clear()
        stored.sync()

    def test_presets_match_approved_result(self) -> None:
        """Значения из карточки результата C: birefnet-general и --blur 0.5."""
        self.assertEqual(APP_DEFAULTS["cut/model"], "birefnet-general")
        self.assertEqual(APP_DEFAULTS["cut/tile"], 1024)
        self.assertEqual(APP_DEFAULTS["cut/sigma"], 1.4)
        self.assertEqual(APP_DEFAULTS["cut/head_ratio"], 0.34)
        self.assertIs(APP_DEFAULTS["cut/portrait"], True)
        self.assertIs(APP_DEFAULTS["cut/matting"], True)
        self.assertEqual(APP_DEFAULTS["compose/blur"], 0.5)
        self.assertEqual(APP_DEFAULTS["compose/shadow"], 0.22)
        self.assertEqual(APP_DEFAULTS["compose/tone"], 1.06)
        self.assertEqual(APP_DEFAULTS["compose/grain"], 4.5)
        self.assertEqual(APP_DEFAULTS["compose/seed"], 7)
        self.assertEqual(APP_DEFAULTS["upscale/factor"], 2)
        self.assertNotIn("models/upscale", APP_DEFAULTS)
        self.assertNotEqual(APP_DEFAULTS["cut/model"], "u2netp")

    def test_apply_writes_all_presets_once(self) -> None:
        stored = app_settings()
        self.assertTrue(apply_default_presets(stored))
        for key, value in APP_DEFAULTS.items():
            self.assertEqual(stored.value(key), value, key)
        self.assertEqual(stored.value("app/defaults_version"), DEFAULTS_VERSION)

        # Повторный запуск ничего не меняет.
        self.assertFalse(apply_default_presets(app_settings()))

    def test_apply_removes_legacy_upscale_model(self) -> None:
        stored = app_settings()
        stored.setValue("models/upscale", "realesr-general-x4v3")
        stored.sync()
        apply_default_presets(stored)
        self.assertIsNone(stored.value("models/upscale"))

    def test_apply_overwrites_stale_values(self) -> None:
        stored = app_settings()
        # u2net больше нет в списке моделей — миграция вернёт дефолт.
        stored.setValue("cut/model", "u2net")
        stored.setValue("compose/blur", 0.72)
        stored.sync()

        self.assertTrue(apply_default_presets(stored))
        self.assertEqual(stored.value("cut/model"), "birefnet-general")
        self.assertEqual(float(stored.value("compose/blur")), 0.5)

    def test_apply_keeps_u2netp_as_preview_model(self) -> None:
        """Теперь u2netp — допустимая модель превью, а не устаревший ключ."""
        stored = app_settings()
        apply_default_presets(stored)
        stored.setValue("cut/model", "u2netp")
        stored.sync()

        self.assertFalse(apply_default_presets(app_settings()))
        self.assertEqual(app_settings().value("cut/model"), "u2netp")

    def test_apply_repairs_removed_model_without_resetting_params(self) -> None:
        stored = app_settings()
        apply_default_presets(stored)
        stored.setValue("cut/model", "birefnet-massive")
        stored.setValue("compose/blur", 1.1)
        stored.sync()

        self.assertTrue(apply_default_presets(app_settings()))
        self.assertEqual(app_settings().value("cut/model"), "birefnet-general")
        self.assertEqual(float(app_settings().value("compose/blur")), 1.1)

    def test_apply_keeps_user_changes_after_migration(self) -> None:
        stored = app_settings()
        apply_default_presets(stored)
        stored.setValue("cut/model", "birefnet-portrait")
        stored.setValue("compose/blur", 1.2)
        stored.sync()

        self.assertFalse(apply_default_presets(app_settings()))
        self.assertEqual(app_settings().value("cut/model"), "birefnet-portrait")
        self.assertEqual(float(app_settings().value("compose/blur")), 1.2)

    def test_main_window_loads_presets_on_empty_settings(self) -> None:
        apply_default_presets(app_settings())
        window = MainWindow()
        try:
            self.assertEqual(window.cut_model.currentText(), "birefnet-general")
            slider, factor, _, _ = window.sliders["blur"]
            self.assertEqual(slider.value() / factor, 0.5)
            params = window.current_params()
            self.assertEqual(params["cut_model"], "birefnet-general")
            self.assertEqual(params["cut_tile"], 1024)
            self.assertEqual(params["blur"], 0.5)
        finally:
            window.close()
            window.deleteLater()
            self.process_events()

    def test_main_window_persists_model_choice(self) -> None:
        """Комбо на панели задач должно писать cut/model, а не только читать."""
        apply_default_presets(app_settings())
        window = MainWindow()
        try:
            window.cut_model.setCurrentText("u2netp")
            self.assertEqual(app_settings().value("cut/model"), "u2netp")
            self.assertEqual(window.current_params()["cut_model"], "u2netp")
        finally:
            window.close()
            window.deleteLater()
            self.process_events()

    def test_settings_dialog_uses_presets_as_fallback(self) -> None:
        dialog = SettingsDialog()
        try:
            self.assertEqual(dialog.defaults["cut/model"], "birefnet-general")
            self.assertEqual(dialog.defaults["compose/blur"], 0.5)
            self.assertEqual(dialog.controls["cut/model"].currentText(), "birefnet-general")
        finally:
            dialog.close()
            dialog.deleteLater()
            self.process_events()
