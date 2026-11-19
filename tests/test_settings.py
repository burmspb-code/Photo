"""Тесты диалога настроек и чтения настроек главным окном."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QFormLayout, QScrollArea, QSizePolicy, QTabWidget

from src.core.cut_params import CUT_DEFAULTS
from src.ui.main_window import CUT_MODELS, MainWindow
from src.ui.settings_dialog import SettingsDialog
from src.ui.styles import THEMES
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

    def test_cut_tab_exposes_every_tunable(self) -> None:
        dialog = SettingsDialog()
        try:
            for key in CUT_DEFAULTS:
                self.assertIn(f"cut/{key}", dialog.controls, key)
            self.assertIn("cut/model", dialog.controls)
            self.assertIn("cut/format", dialog.controls)
        finally:
            dialog.close()
            dialog.deleteLater()
            self.process_events()

    def test_cut_content_background_follows_theme(self) -> None:
        # QSS задаёт фон через objectName; без него вьюпорт остаётся системным
        # светлым и светлый текст тёмной темы становится нечитаемым.
        dialog = SettingsDialog()
        try:
            scroll = dialog.findChild(QScrollArea)
            viewport = scroll.viewport()
            content = scroll.widget()
            self.assertEqual(viewport.objectName(), "settingsCutViewport")
            self.assertEqual(content.objectName(), "settingsCutContent")
            for theme in THEMES:
                with self.subTest(theme=theme):
                    self.assertIn(f"QWidget#{viewport.objectName()}", THEMES[theme])
                    self.assertIn(f"QWidget#{content.objectName()}", THEMES[theme])
        finally:
            dialog.close()
            dialog.deleteLater()
            self.process_events()

    def test_checkbox_styles_are_explicit_in_both_themes(self) -> None:
        for theme, qss in THEMES.items():
            with self.subTest(theme=theme):
                self.assertNotIn("$", qss)  # все плейсхолдеры подставлены
                for state in ("checked", "hover", "disabled"):
                    self.assertIn(f"QCheckBox::indicator:{state}", qss)
        match = re.search(r'image: url\("([^"]+)"\)', THEMES["Тёмная"])
        self.assertIsNotNone(match)
        self.assertTrue(Path(match.group(1)).is_file(), match.group(1))

    def test_checkbox_indicator_contrast_in_both_themes(self) -> None:
        window = MainWindow()
        try:
            for theme in THEMES:
                with self.subTest(theme=theme):
                    window._apply_theme(theme)
                    dialog = SettingsDialog(window)
                    try:
                        dialog.show()
                        dialog.findChild(QTabWidget).setCurrentIndex(1)
                        self.process_events()
                        box = dialog.controls["cut/portrait"]
                        pos = box.mapTo(dialog, QPoint(0, 0))
                        for checked in (True, False):
                            box.setChecked(checked)
                            self.process_events()
                            image = QImage(dialog.size(), QImage.Format.Format_ARGB32)
                            image.fill(QColor(0, 0, 0, 0))
                            dialog.render(image)
                            colors = Counter()
                            for y in range(pos.y(), min(pos.y() + box.height(), image.height())):
                                for x in range(pos.x(), min(pos.x() + 12, image.width())):
                                    c = QColor(image.pixelColor(x, y))
                                    if c.alpha():
                                        colors[(c.red(), c.green(), c.blue())] += 1
                            self.assertTrue(colors, theme)
                            dominant = colors.most_common(1)[0][0]
                            if checked:
                                # Отмеченная клетка — насыщенный синий, галочка белая.
                                self.assertGreater(dominant[2], dominant[0] + 100)
                                brightest = max(colors, key=sum)
                                self.assertGreater(sum(brightest), sum(dominant) + 100)
                            elif theme == "Светлая":
                                self.assertTrue(all(v > 200 for v in dominant), dominant)
                            else:
                                self.assertTrue(all(v < 60 for v in dominant), dominant)
                    finally:
                        dialog.close()
                        dialog.deleteLater()
                        self.process_events()
        finally:
            window.close()
            window.deleteLater()
            self.process_events()

    def test_cut_settings_reach_main_window_params(self) -> None:
        stored = app_settings()
        stored.setValue("cut/isolated_ratio", 0.15)
        stored.setValue("cut/isolated", False)
        stored.setValue("cut/overlap", 0.75)
        stored.sync()
        window = MainWindow()
        try:
            params = window.current_params()
            self.assertEqual(params["isolated_ratio"], 0.15)
            self.assertIs(params["isolated"], False)
            self.assertEqual(params["overlap"], 0.75)
            for key in CUT_DEFAULTS:
                self.assertIn(key, params)
        finally:
            window.close()
            window.deleteLater()
            self.process_events()

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
