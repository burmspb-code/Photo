"""Превью big-изображений: обход лимита Qt и честный лог результата."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PyQt6.QtGui import QImage

import src.ui.main_window as mw
from src.core.image import _read, _write
from tests.gui_case import GuiTestCase

IMAGE = Path(__file__).resolve().parents[1] / "data" / "results" / "2026-11-17-park-c" / "source.jpg"
REAL_QIMAGE = QImage


def _qt_refuses_path(path):
    """Имитировать отказ QImage(path) из-за лимита аллокации."""
    def build(*args):
        if len(args) == 1 and str(args[0]) == str(path):
            return REAL_QIMAGE()
        return REAL_QIMAGE(*args)
    build.Format = REAL_QIMAGE.Format
    return build


class TestLargePreview(GuiTestCase):
    def setUp(self) -> None:
        self.window = mw.MainWindow()
        self.window.show()
        self.process_events()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.process_events()

    def test_falls_back_to_cv2_when_qt_rejects_image(self) -> None:
        preview = self.window.previews["Фон"][0]
        with patch("src.ui.main_window.QImage", _qt_refuses_path(IMAGE)):
            self.assertTrue(preview.set_image(IMAGE))
        pixmap = preview.source_pixmap()
        self.assertIsNotNone(pixmap)
        self.assertGreater(pixmap.width(), 0)
        self.assertGreater(pixmap.height(), 0)
        self.assertNotEqual(preview.text(), "Не удалось прочитать изображение")

    def test_fallback_keeps_alpha(self) -> None:
        with tempfile.TemporaryDirectory(prefix="photo-large-") as folder:
            path = Path(folder) / "cut.png"
            rgba = np.zeros((8, 8, 4), dtype=np.uint8)
            rgba[:, :, :3] = (10, 20, 30)
            rgba[0, 0, 3] = 0
            rgba[1, 1, 3] = 255
            _write(path, rgba)
            preview = self.window.previews["Вырезка"][0]
            with patch("src.ui.main_window.QImage", _qt_refuses_path(path)):
                self.assertTrue(preview.set_image(path))
            pixmap = preview.source_pixmap()
            self.assertIsNotNone(pixmap)
            self.assertTrue(pixmap.toImage().hasAlphaChannel())

    def test_set_background_reports_failure(self) -> None:
        with (
            patch("src.ui.main_window.QImage", _qt_refuses_path(IMAGE)),
            patch("src.ui.main_window._read", return_value=None),
        ):
            self.assertFalse(self.window._set_background(IMAGE))
        self.assertIsNone(self.window.background_path)
        self.assertIn("Не удалось показать фон", self.window.log_display.toPlainText())

    def test_compose_failure_to_show_result_is_not_logged_as_ok(self) -> None:
        result = Path(tempfile.gettempdir()) / "photo-compose-fail.jpg"
        _write(result, np.zeros((8, 8, 3), dtype=np.uint8))
        try:
            self.window.source_path = IMAGE
            self.window.background_path = IMAGE
            cut = Path(tempfile.gettempdir()) / "photo-compose-cut.png"
            _write(cut, np.zeros((8, 8, 4), dtype=np.uint8))
            with (
                patch("src.ui.main_window.CUTOUT_FILE", cut),
                patch("src.ui.main_window.compose_task", return_value=str(result)),
                patch("src.ui.main_window.QImage", _qt_refuses_path(result)),
                patch("src.ui.main_window._read", return_value=None),
            ):
                self.window.tb_compose.trigger()
                self._finish()
            logs = self.window.log_display.toPlainText()
            self.assertIn("Не удалось показать", logs)
            self.assertNotIn("[OK] Сборка композита", logs)
            self.assertEqual(self.window.tabs.tabText(self.window.tabs.currentIndex()), "Результат")
        finally:
            result.unlink(missing_ok=True)
            (Path(tempfile.gettempdir()) / "photo-compose-cut.png").unlink(missing_ok=True)

    def test_scaled_qimage_limits_side(self) -> None:
        big = REAL_QIMAGE(5000, 3000, REAL_QIMAGE.Format.Format_RGB888)
        big.fill(0)
        scaled = mw._scaled_qimage(big)
        self.assertEqual(max(scaled.width(), scaled.height()), mw.MAX_PREVIEW_SIDE)
        self.assertEqual(scaled.height(), round(3000 * mw.MAX_PREVIEW_SIDE / 5000))

        small = REAL_QIMAGE(100, 80, REAL_QIMAGE.Format.Format_RGB888)
        self.assertIs(mw._scaled_qimage(small), small)

    def test_large_preview_downscaled_but_full_path_kept(self) -> None:
        with tempfile.TemporaryDirectory(prefix="photo-large-") as folder:
            path = Path(folder) / "big.jpg"
            _write(path, np.zeros((2200, 4300, 3), dtype=np.uint8))
            preview = self.window.previews["Фон"][0]
            self.assertTrue(preview.set_image(path))
            pixmap = preview.source_pixmap()
            self.assertIsNotNone(pixmap)
            self.assertLessEqual(max(pixmap.width(), pixmap.height()), mw.MAX_PREVIEW_SIDE)
            self.assertEqual(preview.source_path(), str(path))

            preview.clear_image()
            self.assertIsNone(preview.source_path())

    def test_cv2_fallback_downscales_large_image(self) -> None:
        with tempfile.TemporaryDirectory(prefix="photo-large-") as folder:
            path = Path(folder) / "big.jpg"
            _write(path, np.zeros((2200, 4300, 3), dtype=np.uint8))
            preview = self.window.previews["Фон"][0]
            with patch("src.ui.main_window.QImage", _qt_refuses_path(path)):
                self.assertTrue(preview.set_image(path))
            pixmap = preview.source_pixmap()
            self.assertIsNotNone(pixmap)
            self.assertLessEqual(max(pixmap.width(), pixmap.height()), mw.MAX_PREVIEW_SIDE)

    def test_save_preview_full_uses_original_resolution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="photo-large-") as folder:
            src = Path(folder) / "big.jpg"
            _write(src, np.full((2200, 4300, 3), (10, 20, 30), dtype=np.uint8))
            preview = self.window.previews["Фон"][0]
            self.assertTrue(preview.set_image(src))
            out = Path(folder) / "saved.jpg"
            self.assertTrue(self.window._save_preview_full(preview, out, "JPG"))
            self.assertEqual(_read(out).shape[:2], (2200, 4300))

    def test_save_result_full_resolution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="photo-large-") as folder:
            src = Path(folder) / "result-src.jpg"
            _write(src, np.zeros((2200, 4300, 3), dtype=np.uint8))
            self.window.previews["Результат"][0].set_image(src)
            out_dir = Path(folder) / "out"
            with patch("src.ui.main_window.DATA_DIR", out_dir):
                self.window.save_result()
            saved = _read(out_dir / "result.jpg")
            self.assertEqual(saved.shape[:2], (2200, 4300))

    def test_save_current_full_resolution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="photo-large-") as folder:
            src = Path(folder) / "bg-src.jpg"
            _write(src, np.zeros((2200, 4300, 3), dtype=np.uint8))
            self.window.previews["Фон"][0].set_image(src)
            self.window.tabs.setCurrentIndex(2)
            out = Path(folder) / "saved-bg.jpg"
            with patch("src.ui.main_window.QFileDialog.getSaveFileName",
                       return_value=(str(out), "")):
                self.window.save_current()
            self.assertEqual(_read(out).shape[:2], (2200, 4300))

    def test_save_before_after_full_resolution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="photo-large-") as folder:
            before = Path(folder) / "before.jpg"
            after = Path(folder) / "after.jpg"
            _write(before, np.zeros((2200, 3000, 3), dtype=np.uint8))
            _write(after, np.zeros((1100, 2000, 3), dtype=np.uint8))
            self.window.previews["До — После"][0].set_image(before)
            self.window.previews["До — После"][1].set_image(after)
            self.window.tabs.setCurrentIndex(4)
            out = Path(folder) / "compare.jpg"
            with patch("src.ui.main_window.QFileDialog.getSaveFileName",
                       return_value=(str(out), "")):
                self.window.save_current()
            saved = _read(out)
            # after 1100×2000 → 2200×4000, плюс зазор 6 px
            self.assertEqual(saved.shape[:2], (2200, 3000 + 6 + 4000))

    def _finish(self) -> None:
        worker = self.window._worker
        self.assertIsNotNone(worker)
        worker.wait(20000)
        self.process_events()
