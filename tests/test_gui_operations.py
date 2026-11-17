"""Тесты подключения core к GUI: запуск, результат, ошибка, отмена."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.core.image import _write
from src.ui.main_window import MainWindow
from tests.gui_case import GuiTestCase

IMAGE = Path(__file__).resolve().parents[1] / "data" / "results" / "2026-11-17-park-c" / "source.jpg"


class TestGuiOperations(GuiTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="photo-operations-")
        self.dir = Path(self._tmp.name)
        self.window = MainWindow()
        self.window.show()
        self.process_events()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.process_events()
        self._tmp.cleanup()

    def _image(self, name: str, channels: int = 3) -> Path:
        path = self.dir / name
        _write(path, np.zeros((8, 10, channels), np.uint8))
        return path

    def _finish(self):
        worker = self.window._worker
        self.assertIsNotNone(worker)
        self.assertTrue(worker.wait(5000))
        self.process_events()
        return worker

    def test_cut_without_source_does_not_start(self) -> None:
        self.window.tb_cut.trigger()
        self.process_events()
        self.assertIsNone(self.window._worker)
        self.assertIn("откройте исходное фото", self.window.log_display.toPlainText())

    def test_cut_success_updates_preview_and_controls(self) -> None:
        cut = self._image("cut.png", 4)

        def fake(src, out=None, options=None, progress=None, cancelled=None):
            progress(50, "половина")
            return str(cut)

        with patch("src.ui.main_window.cut_task", side_effect=fake):
            self.window.source_path = IMAGE
            self.window.tb_cut.trigger()
            self.assertTrue(self.window.tb_stop.isEnabled())
            self.assertFalse(self.window.tb_cut.isEnabled())
            self._finish()

        self.assertIsNone(self.window._worker)
        self.assertTrue(self.window.tb_cut.isEnabled())
        self.assertFalse(self.window.tb_stop.isEnabled())
        self.assertIsNotNone(self.window.previews["Вырезка"][0].source_pixmap())
        self.assertEqual(self.window.progress.value(), 50)
        self.assertIn("cut.png", self.window.log_display.toPlainText())

    def test_failed_operation_logs_error(self) -> None:
        with patch("src.ui.main_window.cut_task", side_effect=RuntimeError("сбой ядра")):
            self.window.source_path = IMAGE
            self.window.tb_cut.trigger()
            self._finish()
        self.assertIn("RuntimeError: сбой ядра", self.window.log_display.toPlainText())
        self.assertTrue(self.window.tb_cut.isEnabled())

    def test_stop_cancels_running_operation(self) -> None:
        cut = self._image("cut.png", 4)

        def fake(src, out=None, options=None, progress=None, cancelled=None):
            for step in range(200):
                if cancelled():
                    return None
                progress(step % 100, "работа")
                time.sleep(0.01)
            return str(cut)

        with patch("src.ui.main_window.cut_task", side_effect=fake):
            self.window.source_path = IMAGE
            self.window.tb_cut.trigger()
            self.process_events()
            self.window.btn_stop.click()
            self._finish()

        self.assertIn("отменено", self.window.log_display.toPlainText())
        self.assertIsNone(self.window.previews["Вырезка"][0].source_pixmap())
        self.assertFalse(self.window.btn_stop.isEnabled())

    def test_stop_when_idle_keeps_old_message(self) -> None:
        self.window.stop_operation()
        self.assertIn("останавливать нечего", self.window.log_display.toPlainText())

    def test_generate_success_sets_background(self) -> None:
        background = self._image("generated.jpg")
        with patch("src.ui.main_window.genbg_task", return_value=str(background)):
            self.window.tb_generate.trigger()
            self._finish()
        self.assertEqual(self.window.background_path, background)
        self.assertIsNotNone(self.window.previews["Фон"][0].source_pixmap())

    def test_generate_without_prompt_does_not_start(self) -> None:
        self.window.prompt.clear()
        self.window.tb_generate.trigger()
        self.assertIsNone(self.window._worker)
        self.assertIn("введите промпт", self.window.log_display.toPlainText())

    def test_upscale_requires_background(self) -> None:
        self.window.tb_upscale.trigger()
        self.assertIsNone(self.window._worker)
        self.assertIn("выберите фон", self.window.log_display.toPlainText())

    def test_compose_requires_cutout(self) -> None:
        self.window.source_path = IMAGE
        self.window.background_path = self._image("bg.jpg")
        with patch("src.ui.main_window.CUTOUT_FILE", self.dir / "missing.png"):
            self.window.tb_compose.trigger()
        self.assertIsNone(self.window._worker)
        self.assertIn("вырежьте объект", self.window.log_display.toPlainText())

    def test_compose_success_updates_result_tabs(self) -> None:
        cut = self._image("cut.png", 4)
        result = self._image("result.jpg")
        self.window.source_path = IMAGE
        self.window.background_path = self._image("bg.jpg")
        self.window.previews["До — После"][0].set_image(IMAGE)
        with (
            patch("src.ui.main_window.CUTOUT_FILE", cut),
            patch("src.ui.main_window.compose_task", return_value=str(result)),
        ):
            self.window.tb_compose.trigger()
            self._finish()
        self.assertIsNotNone(self.window.previews["Результат"][0].source_pixmap())
        self.assertIsNotNone(self.window.previews["До — После"][1].source_pixmap())
        self.assertIn("result.jpg", self.window.log_display.toPlainText())
