"""Тесты диалога настроек и чтения настроек главным окном."""
from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget

from src.ui.main_window import CUT_MODELS, MainWindow
from src.ui.settings_dialog import SettingsDialog
from tests.gui_case import GuiTestCase, app_settings


class TestSettingsDialog(GuiTestCase):
    def setUp(self) -> None:
        stored = app_settings()
        stored.clear()
        stored.sync()

    def test_tabs(self) -> None:
        dialog = SettingsDialog()
        tabs = dialog.findChild(QTabWidget)
        self.assertEqual(
            [tabs.tabText(i) for i in range(tabs.count())],
            ["Модели", "Вырезка", "Фон", "Композит", "Апскейл", "Пути", "Общие"],
        )

    def test_upscale_factor_combo_saves_number_and_loads_it(self) -> None:
        dialog = SettingsDialog()
        combo = dialog.controls["upscale/factor"]
        self.assertEqual(combo.currentData(), 2)
        combo.setCurrentIndex(1)
        dialog._save()
        self.assertEqual(app_settings().value("upscale/factor"), 4)

        dialog = SettingsDialog()
        self.assertEqual(dialog.controls["upscale/factor"].currentData(), 4)

    def test_main_window_reads_upscale_factor(self) -> None:
        stored = app_settings()
        stored.setValue("upscale/factor", 4)
        stored.sync()
        window = MainWindow()
        try:
            self.assertEqual(window.current_params()["upscale_factor"], 4)
            self.assertIn("×4", window.tb_upscale.toolTip())
        finally:
            window.close()
            window.deleteLater()
            self.process_events()

    def test_save_persists_values(self) -> None:
        dialog = SettingsDialog()
        model = CUT_MODELS[-1]
        dialog.controls["cut/model"].setCurrentText(model)
        dialog._save()

        stored = app_settings()
        self.assertEqual(stored.value("cut/model"), model)

    def test_main_window_reads_float_compose_values(self) -> None:
        stored = app_settings()
        stored.setValue("compose/blur", 0.72)
        stored.sync()

        window = MainWindow()
        try:
            slider, factor, label, _ = window.sliders["blur"]
            self.assertEqual(factor, 10)
            self.assertEqual(slider.value(), 7)
            self.assertIn("0.7", label.text())
        finally:
            window.close()
            window.deleteLater()
            self.process_events()
