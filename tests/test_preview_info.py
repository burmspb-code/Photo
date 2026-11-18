"""Подпись в шапке превью: имя файла и разрешение из заголовка файла."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from src.core.image import _write
from src.ui.main_window import MainWindow
from tests.gui_case import GuiTestCase


class TestPreviewInfo(GuiTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="photo-preview-info-")
        self.dir = Path(self._tmp.name)
        self.window = MainWindow()
        self.window.show()
        self.process_events()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.process_events()
        self._tmp.cleanup()

    def _image(self, name: str, width: int = 120, height: int = 80) -> Path:
        path = self.dir / name
        _write(path, np.full((height, width, 3), 128, np.uint8))
        return path

    @property
    def info(self) -> str:
        return self.window.preview_info._full_text

    def test_header_starts_empty(self) -> None:
        self.assertEqual(self.info, "")
        self.assertEqual(self.window.preview_info.toolTip(), "")

    def test_load_shows_name_and_real_resolution(self) -> None:
        image = self._image("source.png", 163, 122)
        self.window.previews["Исходник"][0].set_image(image)
        self.process_events()
        self.assertEqual(self.info, "source.png · 163×122")
        # В узком окне подпись сокращается по середине, но начало и конец видны.
        shown = self.window.preview_info.text()
        self.assertIn("source", shown)
        self.assertIn("122", shown)
        self.assertIn(str(image), self.window.preview_info.toolTip())
        self.assertIn("МБ", self.window.preview_info.toolTip())

    def test_switching_tabs_updates_info(self) -> None:
        source = self._image("source.png", 100, 60)
        background = self._image("background.jpg", 200, 120)
        self.window.previews["Исходник"][0].set_image(source)
        self.window.previews["Фон"][0].set_image(background)

        self.window.tabs.setCurrentIndex(0)
        self.process_events()
        self.assertEqual(self.info, "source.png · 100×60")

        self.window.tabs.setCurrentIndex(2)
        self.process_events()
        self.assertEqual(self.info, "background.jpg · 200×120")

    def test_clear_resets_info(self) -> None:
        image = self._image("cut.png")
        self.window.tabs.setCurrentIndex(1)
        self.window.previews["Вырезка"][0].set_image(image)
        self.process_events()
        self.assertIn("cut.png", self.info)

        self.window.clear_current()
        self.process_events()
        self.assertEqual(self.info, "")
        self.assertEqual(self.window.preview_info.toolTip(), "")

    def test_comparison_tab_shows_both_files(self) -> None:
        before = self._image("before.jpg", 320, 240)
        after = self._image("after.jpg", 640, 480)
        self.window.previews["До — После"][0].set_image(before)
        self.window.previews["До — После"][1].set_image(after)
        self.window.tabs.setCurrentIndex(4)
        self.process_events()
        self.assertEqual(self.info, "before.jpg · 320×240  →  after.jpg · 640×480")
        self.assertIn(str(before), self.window.preview_info.toolTip())
        self.assertIn(str(after), self.window.preview_info.toolTip())

    def test_oversized_preview_reports_real_file_resolution(self) -> None:
        big = self._image("big.jpg", 4200, 100)
        self.window.previews["Фон"][0].set_image(big)
        self.window.tabs.setCurrentIndex(2)
        self.process_events()
        self.assertEqual(self.info, "big.jpg · 4200×100")
