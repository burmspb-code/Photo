"""Тесты диалога настроек и чтения настроек главным окном."""
from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QSizePolicy, QTabWidget

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

    def test_background_tab_rows_are_compact(self) -> None:
        dialog = SettingsDialog()
        try:
            dialog.show()
            self.process_events()
            page = dialog.findChild(QTabWidget).widget(2)
            form = page.layout()
            self.assertEqual(
                dialog.controls["bg/prompt"].sizePolicy().verticalPolicy(),
                QSizePolicy.Policy.Fixed,
            )
            ys = [
                form.itemAt(row, QFormLayout.ItemRole.FieldRole).geometry().y()
                for row in range(form.rowCount())
            ]
            self.assertLess(ys[-1] - ys[0], 200)
        finally:
            dialog.close()
            dialog.deleteLater()
            self.process_events()

    def test_dead_background_fields_are_gone(self) -> None:
        dialog = SettingsDialog()
        self.assertNotIn("bg/drafts", dialog.controls)
        self.assertNotIn("bg/aspect", dialog.controls)

    def test_upscale_factor_combo_saves_number_and_loads_it(self) -> None:
        dialog = SettingsDialog()
        combo = dialog.controls["upscale/factor"]
        self.assertEqual(combo.currentData(), 2)
        combo.setCurrentIndex(1)
        dialog._save()
        self.assertEqual(app_settings().value("upscale/factor"), 4)

        dialog = SettingsDialog()
        self.assertEqual(dialog.controls["upscale/factor"].currentData(), 4)

    def test_hints_checkbox_saves_and_main_window_honors_it(self) -> None:
        dialog = SettingsDialog()
        checkbox = dialog.controls["ui/hints"]
        self.assertTrue(checkbox.isChecked())
        checkbox.setChecked(False)
        dialog._save()
        self.assertIs(app_settings().value("ui/hints", type=bool), False)

        dialog = SettingsDialog()
        self.assertFalse(dialog.controls["ui/hints"].isChecked())

        window = MainWindow()
        try:
            self.assertNotIn("[HINT]", window.log_display.toPlainText())
        finally:
            window.close()
            window.deleteLater()
            self.process_events()

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
