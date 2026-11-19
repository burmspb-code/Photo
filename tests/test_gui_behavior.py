"""Функциональные тесты MainWindow: масштаб, сохранение, темы и оверлеи."""
from __future__ import annotations

import math
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QSplitter

from src.ui.main_window import PARAMS_WIDTH, ZOOM_MAX, ZOOM_MIN, MainWindow
from tests.gui_case import GuiTestCase
from tests.test_gui_helpers import dominant_color

RESULT = Path(__file__).resolve().parents[1] / "data" / "results" / "2026-11-17-park-c"
IMAGE = RESULT / "source.jpg"


class TestMainWindow(GuiTestCase):
    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.process_events()
        self.area = self.window.preview_area_controls

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.process_events()

    def send_wheel(self, angle: int = 120) -> None:
        event = QWheelEvent(
            QPointF(80, 80), QPointF(80, 80), QPoint(0, 0), QPoint(0, angle),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False,
        )
        QApplication.sendEvent(self.area, event)

    def probe_interactions(self) -> tuple[int, int]:
        """Имитирует колесо и движение ползунка масштаба."""
        counts = {"wheel": 0}
        connection = self.area.wheel_stepped.connect(lambda _: counts.__setitem__("wheel", 1))
        self.send_wheel()
        self.window.zoom_slider.setValue(50)
        self.process_events()
        self.area.wheel_stepped.disconnect(connection)
        return counts["wheel"], self.window.zoom_slider.value()

    def load_current(self) -> None:
        index = self.window.tabs.currentIndex()
        self.window.previews[self.window.tabs.tabText(index)][0].set_image(str(IMAGE))

    def test_window_centered_with_85_percent_area(self) -> None:
        area = self.window.screen().availableGeometry()
        geometry = self.window.geometry()
        scale = math.sqrt(0.85)
        expected_w = max(self.window.minimumWidth(), round(area.width() * scale))
        expected_h = max(self.window.minimumHeight(), round(area.height() * scale))
        self.assertEqual((geometry.width(), geometry.height()), (expected_w, expected_h))
        self.assertLessEqual(abs(geometry.center().x() - area.center().x()), 1)
        self.assertLessEqual(abs(geometry.center().y() - area.center().y()), 1)

    def test_zoom_scale_and_labels(self) -> None:
        slider = self.window.zoom_slider
        self.assertEqual((slider.minimum(), slider.maximum()), (ZOOM_MIN, ZOOM_MAX))
        labels = self.area.zoom_overlay.findChildren(QLabel)
        self.assertEqual([label.text() for label in labels], ["×4", "×2", "×1", "÷2"])

    def test_zoom_labels_aligned_with_slider_handle(self) -> None:
        slider = self.window.zoom_slider.geometry()
        labels = self.area.zoom_overlay.findChildren(QLabel)
        centers = [label.geometry().center().y() for label in labels]
        # Ручка высотой 10 px: её центр ходит от top+5 до bottom−5.
        self.assertLessEqual(abs(centers[0] - (slider.top() + 5)), 2)
        self.assertLessEqual(abs(centers[-1] - (slider.bottom() - 5)), 2)
        step = (centers[-1] - centers[0]) / 3
        for index, center in enumerate(centers):
            self.assertAlmostEqual(center, centers[0] + index * step, delta=1)

    def test_zoom_wheel_clamped_to_magnification_range(self) -> None:
        self.load_current()
        slider = self.window.zoom_slider
        for _ in range(50):
            self.send_wheel()
        self.assertEqual(slider.value(), ZOOM_MAX)
        for _ in range(80):  # 300/5 = 60 шагов от +200 до −100
            self.send_wheel(-120)
        self.assertEqual(slider.value(), ZOOM_MIN)

    def test_zoom_values_map_to_fit_factor(self) -> None:
        self.load_current()
        preview = self.window.previews[self.window.tabs.tabText(self.window.tabs.currentIndex())][0]
        fit = preview.fit_factor()
        self.assertGreater(fit, 0)

        self.window.zoom_slider.setValue(0)
        self.assertEqual(preview.zoom, 0.0)
        self.window.zoom_slider.setValue(-100)
        self.assertAlmostEqual(preview.zoom, fit / 2, delta=fit * 0.01)
        self.window.zoom_slider.setValue(100)
        self.assertAlmostEqual(preview.zoom, fit * 2, delta=fit * 0.01)
        self.window.zoom_slider.setValue(200)
        self.assertAlmostEqual(preview.zoom, fit * 4, delta=fit * 0.01)

    def test_zoom_synced_when_returning_to_tab(self) -> None:
        self.load_current()
        self.window.zoom_slider.setValue(-50)
        self.window.tabs.setCurrentIndex(2)  # пустой «Фон»
        self.window.tabs.setCurrentIndex(0)
        self.process_events()
        self.assertEqual(self.window.zoom_slider.value(), -50)

    def test_interactions_blocked_only_for_empty_current_tab(self) -> None:
        # Пустая вкладка.
        self.assertEqual(self.probe_interactions(), (0, 0))

        # Загруженный «Исходник», но пустые остальные вкладки.
        self.load_current()
        for index, title in ((1, "Вырезка"), (2, "Фон"), (3, "Результат")):
            self.window.tabs.setCurrentIndex(index)
            with self.subTest(tab=title):
                self.assertEqual(self.probe_interactions(), (0, 0))
        self.assertIsNone(self.window.background_path)
        self.assertIsNone(self.window.previews["Фон"][0].source_pixmap())

        # Загруженный «Исходник».
        self.window.tabs.setCurrentIndex(0)
        self.assertTrue(any(self.probe_interactions()))

        # Загруженный «Результат».
        self.window.tabs.setCurrentIndex(3)
        self.load_current()
        self.assertTrue(any(self.probe_interactions()))

        # «До — После» с одной загруженной половиной.
        self.window.previews["До — После"][0].set_image(str(IMAGE))
        self.window.tabs.setCurrentIndex(4)
        self.assertTrue(any(self.probe_interactions()))

    def test_zoom_overlay_hidden_without_image(self) -> None:
        overlay = self.area.zoom_overlay
        overlay._timer.stop()
        self.assertFalse(overlay.can_reveal())
        overlay.reveal()
        self.assertFalse(overlay._timer.isActive())

        self.load_current()
        self.assertTrue(overlay.can_reveal())
        overlay.reveal()
        self.assertTrue(overlay._timer.isActive())

    def test_zoom_overlay_inside_preview_page(self) -> None:
        page = self.area._page_rect()
        self.assertTrue(page.contains(self.area.zoom_overlay.geometry()))

    def test_pan_cursor_shapes(self) -> None:
        self.load_current()
        preview = self.window.previews[self.window.tabs.tabText(0)][0]
        QApplication.sendEvent(preview, QEvent(QEvent.Type.Enter))
        self.assertEqual(preview.cursor().shape(), Qt.CursorShape.OpenHandCursor)
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(20, 20),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(preview, press)
        self.assertEqual(preview.cursor().shape(), Qt.CursorShape.ClosedHandCursor)
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(20, 20),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(preview, release)
        self.assertEqual(preview.cursor().shape(), Qt.CursorShape.OpenHandCursor)

    def test_save_button_in_tab_row_disabled_for_source_and_empty_tabs(self) -> None:
        button = self.window.btn_save_current
        corner = self.window.tabs.cornerWidget(Qt.Corner.TopRightCorner)
        self.assertIs(corner.findChild(QPushButton, "saveCurrent"), button)
        self.assertIs(corner.findChild(QPushButton, "clearCurrent"), self.window.btn_clear_current)
        self.assertFalse(button.isEnabled())

        self.load_current()  # «Исходник» — сохранение не предусмотрено
        self.process_events()
        self.assertFalse(button.isEnabled())

        for index, title in ((1, "Вырезка"), (2, "Фон"), (3, "Результат"), (4, "До — После")):
            self.window.tabs.setCurrentIndex(index)
            with self.subTest(tab=title):
                self.assertFalse(button.isEnabled())

    def test_save_button_enabled_only_for_intermediate_tabs_with_image(self) -> None:
        button = self.window.btn_save_current
        for index, title in ((1, "Вырезка"), (2, "Фон"), (3, "Результат")):
            self.window.tabs.setCurrentIndex(index)
            self.load_current()
            self.process_events()
            with self.subTest(tab=title):
                self.assertTrue(button.isEnabled())

        self.window.tabs.setCurrentIndex(4)
        self.load_current()  # только левая половина «До — После»
        self.assertFalse(button.isEnabled())
        self.window.previews["До — После"][1].set_image(str(IMAGE))
        self.process_events()
        self.assertTrue(button.isEnabled())

    def test_background_navigation_removed(self) -> None:
        self.assertFalse(hasattr(self.window, "_cycle_background"))
        self.assertFalse(hasattr(self.area, "nav_overlay"))

    def test_theme_switch_keeps_icon_colors(self) -> None:
        names = ("tb_open_source", "tb_open_background", "tb_cut", "tb_generate",
                 "tb_upscale", "tb_compose", "tb_stop", "tb_save", "btn_save_current")
        self.window._apply_theme("Тёмная")
        self.process_events()
        before = {name: dominant_color(getattr(self.window, name).icon()) for name in names}
        dark_style = self.window.styleSheet()

        self.window._apply_theme("Светлая")
        self.process_events()

        self.assertNotEqual(self.window.styleSheet(), dark_style)
        self.assertFalse(self.window.act_theme_dark.isChecked())
        self.assertTrue(self.window.act_theme_light.isChecked())
        self.assertEqual(self.window.settings.value("ui/theme"), "Светлая")
        after = {name: dominant_color(getattr(self.window, name).icon()) for name in names}
        self.assertEqual(after, before)

    def test_folder_icons_present(self) -> None:
        for name in ("tb_open_source", "tb_open_background", "btn_pick_source",
                     "btn_pick_background", "btn_save_current"):
            with self.subTest(name=name):
                self.assertFalse(getattr(self.window, name).icon().isNull())

    def _top_splitter(self) -> QSplitter:
        """Горизонтальный сплиттер: панель задач | превью."""
        return next(
            splitter for splitter in self.window.findChildren(QSplitter)
            if "Horizontal" in str(splitter.orientation())
        )

    def _assert_params_width_fixed(self, stage: str) -> None:
        zone = self.window.params_zone
        with self.subTest(stage=stage):
            self.assertEqual(zone.width(), PARAMS_WIDTH)
            self.assertEqual(zone.minimumWidth(), PARAMS_WIDTH)
            self.assertEqual(zone.maximumWidth(), PARAMS_WIDTH)
            self.assertEqual(self._top_splitter().sizes()[0], PARAMS_WIDTH)

    def test_params_panel_width_stays_fixed(self) -> None:
        """Панель задач не убегает при путях, промпте, resize и загрузке."""
        self.process_events()
        self._assert_params_width_fixed("start")

        # Длинный путь без точек разрыва раньше давал minimumSizeHint() ~1200 px.
        self.window.lbl_source.setText(
            r"C:\Users\bur_s\OneDrive\Изображения\Архив\2026\Отборка"
            r"\DSC00103_original_very_long_file_name_for_test.jpg"
        )
        self.window.lbl_background.setText(
            r"C:\My_projects\Photo\data\bg\generated-20261118-012746-from-settings.jpg"
        )
        self.process_events()
        self._assert_params_width_fixed("long paths")

        self.window.prompt.setPlainText(
            "realistic photo, rocky coast of the Arctic Ocean, seagulls "
            "circling over the shore, overcast sky"
        )
        self.process_events()
        self._assert_params_width_fixed("prompt")

        self.window.resize(1600, 1000)
        self.process_events()
        self._assert_params_width_fixed("resize")

        # Имитация загрузки картинки: превью меняет sizeHint, панель — нет.
        self.load_current()
        self.process_events()
        self._assert_params_width_fixed("image loaded")

        self.window.prompt.clear()
        self.process_events()
        self._assert_params_width_fixed("prompt cleared")
