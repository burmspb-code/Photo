"""Кнопка «Очистить» сбрасывает предпросмотр этапа и блокирует сохранение."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from src.core.image import _write
from src.ui.main_window import MainWindow
from tests.gui_case import GuiTestCase

IMAGE = Path(__file__).resolve().parents[1] / "data" / "results" / "2026-11-17-park-c" / "source.jpg"
TABS = ((1, "Вырезка"), (2, "Фон"), (3, "Результат"), (4, "До — После"))


class TestClearPreviews(GuiTestCase):
    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.process_events()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.process_events()

    def _load(self, tab: str) -> None:
        for preview in self.window.previews[tab]:
            preview.set_image(str(IMAGE))
        self.process_events()

    def test_clear_button_sits_next_to_save_in_tab_row(self) -> None:
        corner = self.window.tabs.cornerWidget(Qt.Corner.TopRightCorner)
        clear = corner.findChild(QPushButton, "clearCurrent")
        save = corner.findChild(QPushButton, "saveCurrent")
        self.assertIs(clear, self.window.btn_clear_current)
        self.assertIs(save, self.window.btn_save_current)
        self.assertLess(corner.layout().indexOf(clear), corner.layout().indexOf(save))
        self.assertEqual(clear.text(), "Очистить")

    def test_clear_hidden_for_source_and_disabled_for_empty_tabs(self) -> None:
        clear = self.window.btn_clear_current
        self.assertTrue(clear.isHidden())

        for index, _title in TABS:
            self.window.tabs.setCurrentIndex(index)
            self.process_events()
            with self.subTest(tab=self.window.tabs.tabText(index)):
                self.assertFalse(clear.isHidden())
                self.assertFalse(clear.isEnabled())

        self.window.tabs.setCurrentIndex(0)
        self.process_events()
        self.assertTrue(clear.isHidden())

    def test_clear_resets_preview_and_blocks_save_on_every_tab(self) -> None:
        clear = self.window.btn_clear_current
        save = self.window.btn_save_current

        for index, title in TABS:
            self.window.tabs.setCurrentIndex(index)
            self._load(title)
            self.assertTrue(save.isEnabled())
            self.assertTrue(clear.isEnabled())

            clear.click()
            self.process_events()
            with self.subTest(tab=title):
                self.assertTrue(
                    all(preview.source_pixmap() is None for preview in self.window.previews[title])
                )
                self.assertFalse(save.isEnabled())
                self.assertFalse(clear.isEnabled())
                self.assertIn(f"Предпросмотр «{title}» очищен", self.window.log_display.toPlainText())

    def test_clear_background_drops_path_and_label(self) -> None:
        self.window.tabs.setCurrentIndex(2)
        self.window._set_background(IMAGE)
        self.process_events()
        self.assertEqual(self.window.background_path, IMAGE)
        self.assertEqual(self.window.lbl_background.text(), str(IMAGE))

        self.window.btn_clear_current.click()
        self.process_events()
        self.assertIsNone(self.window.background_path)
        self.assertEqual(self.window.lbl_background.text(), "Файл не выбран")
        self.assertFalse(self.window.btn_save_current.isEnabled())

        # Повторный заход во вкладку не должен оживить кнопку.
        self.window.tabs.setCurrentIndex(1)
        self.window.tabs.setCurrentIndex(2)
        self.process_events()
        self.assertFalse(self.window.btn_clear_current.isEnabled())

    def test_clear_keeps_file_on_disk(self) -> None:
        with tempfile.TemporaryDirectory(prefix="photo-clear-") as folder:
            image = Path(folder) / "cutout.png"
            _write(image, np.zeros((8, 8, 4), dtype=np.uint8))
            self.window.tabs.setCurrentIndex(1)
            self.assertTrue(self.window.previews["Вырезка"][0].set_image(str(image)))
            self.process_events()

            self.window.btn_clear_current.click()
            self.process_events()
            self.assertTrue(image.exists())
            self.assertIsNone(self.window.previews["Вырезка"][0].source_pixmap())

    def test_clear_blocked_while_busy(self) -> None:
        self.window.tabs.setCurrentIndex(1)
        self._load("Вырезка")
        self.window._busy = True
        self.window._update_tab_actions()
        self.process_events()
        self.assertFalse(self.window.btn_clear_current.isEnabled())

        self.window.btn_clear_current.click()
        self.process_events()
        self.assertIsNotNone(self.window.previews["Вырезка"][0].source_pixmap())

        self.window._busy = False
        self.window._update_tab_actions()
        self.process_events()
        self.assertTrue(self.window.btn_clear_current.isEnabled())
