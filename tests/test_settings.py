"""Тесты диалога настроек и чтения настроек главным окном."""
from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget

from src.ui.main_window import CUT_MODELS, MainWindow
from src.ui.settings_dialog import SettingsDialog
from tests.gui_case import GuiTestCase, app_settings


class TestSettingsDialog(GuiTestCase):
    def test_tabs(self) -> None:
        dialog = SettingsDialog()
        tabs = dialog.findChild(QTabWidget)
        self.assertEqual(
            [tabs.tabText(i) for i in range(tabs.count())],
            ["Модели", "Вырезка", "Фон", "Композит", "Пути", "Общие"],
        )

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
