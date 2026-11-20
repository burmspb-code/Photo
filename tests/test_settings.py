"""Тесты диалога настроек и чтения настроек главным окном."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QComboBox, QFormLayout, QScrollArea, QSizePolicy, QTabWidget

from src.core.cut_params import CUT_DEFAULTS
from src.ui.animated_combo import AnimatedComboBox
from src.ui.main_window import CUT_MODELS, MainWindow
from src.ui.settings_dialog import SettingsDialog
from src.ui.styles import THEMES, THEME_WINDOW_COLORS
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

    def test_combo_arrow_and_popup_are_styled_in_both_themes(self) -> None:
        """Современная стрелка и popup должны быть полностью стилизованы.

        Если задать ``::drop-down`` без ``::down-arrow`` и состояний
        :hover/:pressed, Qt убирает стрелку и перерисовывает кнопку при
        открытии. Поэтому проверяем наличие всех четырёх правил сразу.
        """
        for theme, qss in THEMES.items():
            with self.subTest(theme=theme):
                self.assertNotIn("$", qss)  # плейсхолдеры подставлены
                for rule in (
                    "QComboBox::drop-down {",
                    "QComboBox::down-arrow {",
                    "QComboBox::drop-down:hover {",
                    "QComboBox::drop-down:pressed {",
                    "QComboBox QAbstractItemView {",
                    "QComboBox QAbstractItemView::item {",
                    "QComboBox QAbstractItemView::item:hover {",
                ):
                    self.assertIn(rule, qss)

                # URL иконки стрелки должен существовать как файл.
                arrow = re.search(r'QComboBox::down-arrow \{\s*image: url\("([^"]+)"\)', qss)
                self.assertIsNotNone(arrow, "не задана иконка стрелки")
                self.assertTrue(Path(arrow.group(1)).is_file(), arrow.group(1))

        # Тёмная тема задаёт тёмный фон списка, светлая — светлый.
        self.assertIn("background: #1e293b;", THEMES["Тёмная"])
        self.assertIn("background: #ffffff;", THEMES["Светлая"])
        # Разные иконки под разные темы, иначе стрелка сливается с полем.
        arrow_re = re.compile(r'QComboBox::down-arrow \{\s*image: url\("([^"]+)"\)')
        dark_arrow = arrow_re.search(THEMES["Тёмная"])
        light_arrow = arrow_re.search(THEMES["Светлая"])
        self.assertIsNotNone(dark_arrow)
        self.assertIsNotNone(light_arrow)
        self.assertNotEqual(dark_arrow.group(1), light_arrow.group(1))

    def test_combo_arrow_is_visible(self) -> None:
        """Стрелка-шеврон должна рисоваться (пиксельная проверка)."""
        window = MainWindow()
        dialog = SettingsDialog(window)
        try:
            combo = dialog.controls["bg/provider_api"]
            img = combo.grab().toImage()
            strip = [
                QColor(img.pixelColor(x, img.height() // 2)).name()
                for x in range(int(img.width() * 0.87), img.width())
            ]
            dominant = Counter(strip).most_common(1)[0][0]
            different = sum(1 for color in strip if color != dominant)
            self.assertGreater(different, 4, "стрелка комбо не видна")
        finally:
            dialog.close()
            dialog.deleteLater()
            window.close()
            window.deleteLater()
            self.process_events()

    def test_spin_arrows_are_styled_in_both_themes(self) -> None:
        """У числовых полей должны быть современные стрелки под обе темы."""
        for theme, qss in THEMES.items():
            with self.subTest(theme=theme):
                self.assertNotIn("$", qss)  # плейсхолдеры подставлены
                for rule in (
                    "QSpinBox::up-button, QDoubleSpinBox::up-button {",
                    "QSpinBox::down-button, QDoubleSpinBox::down-button {",
                    "QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {",
                    "QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {",
                ):
                    self.assertIn(rule, qss)

                for kind in ("up", "down"):
                    arrow = re.search(
                        rf'QSpinBox::{kind}-arrow, QDoubleSpinBox::{kind}-arrow \{{\s*image: url\("([^"]+)"\)',
                        qss,
                    )
                    self.assertIsNotNone(arrow, f"не задана стрелка {kind}")
                    self.assertTrue(Path(arrow.group(1)).is_file(), arrow.group(1))

        # У каждой темы свои иконки, плюс верхняя отличается от нижней.
        def spin_arrow(theme: str, kind: str) -> str:
            match = re.search(
                rf'QSpinBox::{kind}-arrow, QDoubleSpinBox::{kind}-arrow \{{\s*image: url\("([^"]+)"\)',
                THEMES[theme],
            )
            assert match is not None
            return match.group(1)

        for kind in ("up", "down"):
            self.assertNotEqual(spin_arrow("Тёмная", kind), spin_arrow("Светлая", kind))
        for theme in THEMES:
            self.assertNotEqual(spin_arrow(theme, "up"), spin_arrow(theme, "down"))

    def test_spin_arrows_are_visible(self) -> None:
        """Шевроны спинбоксов должны рисоваться (пиксельная проверка)."""
        window = MainWindow()
        dialog = SettingsDialog(window)
        try:
            spin = dialog.controls["cut/tile"]
            img = spin.grab().toImage()
            # Правая полоса кнопок: ищем пиксели стрелок, отличные от фона.
            strip = [
                QColor(img.pixelColor(x, y)).name()
                for x in range(img.width() - 16, img.width())
                for y in range(2, img.height() - 2)
            ]
            dominant = Counter(strip).most_common(1)[0][0]
            different = sum(1 for color in strip if color != dominant)
            self.assertGreater(different, 8, "стрелки спинбокса не видны")
        finally:
            dialog.close()
            dialog.deleteLater()
            window.close()
            window.deleteLater()
            self.process_events()

    def test_all_combos_are_animated(self) -> None:
        """Все комбобоксы приложения должны открываться с анимацией."""
        window = MainWindow()
        dialog = SettingsDialog(window)
        try:
            combos = [w for w in dialog.findChildren(QComboBox)]
            combos.append(window.cut_model)
            self.assertGreater(len(combos), 5)
            for combo in combos:
                with self.subTest(combo=combo.objectName() or combo.currentText()):
                    self.assertIsInstance(combo, AnimatedComboBox)
        finally:
            dialog.close()
            dialog.deleteLater()
            window.close()
            window.deleteLater()
            self.process_events()

    def test_window_colors_match_dialog_background(self) -> None:
        """Цвет для DWM-шапки берётся из той же палитры, что и фон QDialog."""
        for theme, color in THEME_WINDOW_COLORS.items():
            with self.subTest(theme=theme):
                self.assertIn(f"background: {color};", THEMES[theme])

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

    def test_load_restores_model_despite_item_tooltips(self) -> None:
        """Подсказки в элементах комбо не должны ломать чтение QSettings."""
        stored = app_settings()
        stored.setValue("cut/model", "birefnet-portrait")
        stored.sync()

        dialog = SettingsDialog()
        try:
            self.assertEqual(
                dialog.controls["cut/model"].currentText(), "birefnet-portrait"
            )
        finally:
            dialog.close()
            dialog.deleteLater()
            self.process_events()

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
