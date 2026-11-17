"""Тесты подключения core к GUI: запуск, результат, ошибка, отмена."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton

from src.core.image import _write
from src.ui.main_window import DATA_DIR, MainWindow
from src.ui.settings_dialog import SettingsDialog
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

    def test_advisory_toast_hidden_on_startup(self) -> None:
        toast = self.window.advisory_toast
        self.assertTrue(toast.isHidden())
        self.assertEqual(toast._timer.interval(), 5000)

    def test_advisory_shows_toast_and_logs_warning(self) -> None:
        notes = ["Большой кадр 2592×3456: 24 тайла.", "Низкий контраст (σ=31)."]
        with patch("src.ui.main_window.cut_advisory", return_value=notes):
            self.window._update_source_advisory("photo.jpg")
        self.process_events()
        toast = self.window.advisory_toast
        self.assertFalse(toast.isHidden())
        text = toast.label.text()
        self.assertIn("⚠", text)
        for note in notes:
            self.assertIn(note, text)
        self.assertIn("\n", text)  # каждое предупреждение на своей строке
        self.assertTrue(toast._timer.isActive())
        log = self.window.log_display.toPlainText()
        self.assertIn("[WARN]", log)
        self.assertIn("Низкий контраст", log)

    def test_advisory_without_notes_shows_nothing(self) -> None:
        with patch("src.ui.main_window.cut_advisory", return_value=[]):
            self.window._update_source_advisory("photo.jpg")
        self.process_events()
        self.assertTrue(self.window.advisory_toast.isHidden())
        self.assertNotIn("[WARN]", self.window.log_display.toPlainText())

    def test_advisory_toast_close_button_dismisses(self) -> None:
        with patch("src.ui.main_window.cut_advisory", return_value=["Внимание"]):
            self.window._update_source_advisory("photo.jpg")
        self.process_events()
        toast = self.window.advisory_toast
        self.assertFalse(toast.isHidden())
        toast.close_button.click()
        self.process_events()
        self.assertTrue(toast.isHidden())
        self.assertFalse(toast._timer.isActive())

    def test_advisory_toast_fades_on_timeout(self) -> None:
        with patch("src.ui.main_window.cut_advisory", return_value=["Внимание"]):
            self.window._update_source_advisory("photo.jpg")
        toast = self.window.advisory_toast
        toast._timer.timeout.emit()
        self.assertEqual(toast._fade.endValue(), 0.0)

    def test_advisory_toast_close_button_is_visible_without_tooltip(self) -> None:
        with patch("src.ui.main_window.cut_advisory", return_value=["Внимание"]):
            self.window._update_source_advisory("photo.jpg")
        self.process_events()
        toast = self.window.advisory_toast
        self.assertTrue(toast.close_button.isVisible())
        self.assertGreater(toast.close_button.geometry().width(), 0)
        self.assertLessEqual(
            toast.close_button.geometry().top(), toast.label.geometry().top() + 1
        )  # крестик у верхнего края, а не по центру
        self.assertFalse(toast.toolTip())
        self.assertFalse(toast.close_button.toolTip())

    def test_advisory_close_cross_is_centered_in_button(self) -> None:
        with patch("src.ui.main_window.cut_advisory", return_value=["Внимание"]):
            self.window._update_source_advisory("photo.jpg")
        self.process_events()
        button = self.window.advisory_toast.close_button

        image = QImage(button.width(), button.height(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        button.render(painter)
        painter.end()

        # Рамку не трогаем: измеряем только крест внутри квадрата.
        background = image.pixelColor(9, 2)

        def distance(color) -> int:
            return (abs(color.red() - background.red())
                    + abs(color.green() - background.green())
                    + abs(color.blue() - background.blue()))

        ink = [
            (x, y)
            for y in range(3, image.height() - 3)
            for x in range(3, image.width() - 3)
            if distance(image.pixelColor(x, y)) > 60
        ]
        self.assertTrue(ink)
        cx = sum(x for x, _ in ink) / len(ink)
        cy = sum(y for _, y in ink) / len(ink)
        self.assertLessEqual(abs(cx - (button.width() - 1) / 2), 1)
        self.assertLessEqual(abs(cy - (button.height() - 1) / 2), 1)

    def test_advisory_toast_dismisses_when_leaving_source_tab(self) -> None:
        with patch("src.ui.main_window.cut_advisory", return_value=["Внимание"]):
            self.window._update_source_advisory("photo.jpg")
        self.process_events()
        self.assertFalse(self.window.advisory_toast.isHidden())
        self.window.tabs.setCurrentIndex(1)  # «Вырезка»
        self.process_events()
        self.assertTrue(self.window.advisory_toast.isHidden())

    def test_open_source_remembers_last_directory(self) -> None:
        self.window.settings.remove("paths/last_source_dir")
        image = self._image("photo.png")
        with patch("src.ui.main_window.QFileDialog.getOpenFileName",
                   return_value=(str(image), "")) as dialog:
            self.window.open_source()
        self.assertEqual(dialog.call_args.args[2], str(DATA_DIR))
        self.assertEqual(self.window.settings.value("paths/last_source_dir"), str(self.dir))

    def test_open_source_uses_remembered_directory(self) -> None:
        self.window.settings.setValue("paths/last_source_dir", str(self.dir))
        image = self._image("photo2.png")
        with patch("src.ui.main_window.QFileDialog.getOpenFileName",
                   return_value=(str(image), "")) as dialog:
            self.window.open_source()
        self.assertEqual(dialog.call_args.args[2], str(self.dir))

    def test_open_source_activates_source_tab(self) -> None:
        self.window.tabs.setCurrentIndex(1)  # «Вырезка»
        image = self._image("photo.png")
        with patch("src.ui.main_window.QFileDialog.getOpenFileName",
                   return_value=(str(image), "")):
            self.window.open_source()
        self.process_events()
        self.assertEqual(
            self.window.tabs.tabText(self.window.tabs.currentIndex()), "Исходник"
        )

    def test_dialog_start_dir_falls_back_when_folder_is_gone(self) -> None:
        self.window.settings.setValue("paths/last_source_dir", str(self.dir / "gone"))
        self.assertEqual(
            self.window._dialog_start_dir("paths/last_source_dir", DATA_DIR), str(DATA_DIR)
        )

    def test_save_current_writes_png_and_remembers_directory(self) -> None:
        self.window.previews["Вырезка"][0].set_image(self._image("cut.png", 4))
        self.window.tabs.setCurrentIndex(1)
        out = self.dir / "saved-cut.png"
        self.window.settings.remove("paths/last_save_dir")
        with patch("src.ui.main_window.QFileDialog.getSaveFileName",
                   return_value=(str(out), "")) as dialog:
            self.window.btn_save_current.click()
        self.assertTrue(out.exists())
        self.assertTrue(QImage(str(out)).hasAlphaChannel())
        self.assertEqual(Path(dialog.call_args.args[2]).name, "cutout.png")
        self.assertEqual(self.window.settings.value("paths/last_save_dir"), str(self.dir))
        self.assertIn(f"Сохранено (Вырезка): {out}", self.window.log_display.toPlainText())

    def test_save_current_uses_remembered_directory(self) -> None:
        self.window.settings.setValue("paths/last_save_dir", str(self.dir))
        self.window.previews["Фон"][0].set_image(self._image("bg.png"))
        self.window.tabs.setCurrentIndex(2)
        with patch("src.ui.main_window.QFileDialog.getSaveFileName",
                   return_value=("", "")) as dialog:
            self.window.save_current()
        self.assertEqual(Path(dialog.call_args.args[2]), self.dir / "background.jpg")

    def test_save_current_combines_before_and_after(self) -> None:
        before = self.dir / "before.png"
        after = self.dir / "after.png"
        _write(before, np.zeros((20, 40, 3), np.uint8))
        _write(after, np.zeros((10, 30, 3), np.uint8))
        self.window.previews["До — После"][0].set_image(before)
        self.window.previews["До — После"][1].set_image(after)
        self.window.tabs.setCurrentIndex(4)
        out = self.dir / "compare.jpg"
        with patch("src.ui.main_window.QFileDialog.getSaveFileName",
                   return_value=(str(out), "")):
            self.window.save_current()
        image = QImage(str(out))
        self.assertFalse(image.isNull())
        self.assertEqual(image.height(), 20)
        self.assertEqual(image.width(), 40 + 6 + 60)  # две половинки + зазор

    def test_save_current_ignores_source_tab(self) -> None:
        self.window.previews["Исходник"][0].set_image(self._image("source.png"))
        self.window.tabs.setCurrentIndex(0)
        with patch("src.ui.main_window.QFileDialog.getSaveFileName",
                   return_value=(str(self.dir / "x.png"), "")) as dialog:
            self.window.save_current()
        self.assertFalse(dialog.called)

    def test_save_current_blocked_while_busy(self) -> None:
        self.window.previews["Вырезка"][0].set_image(self._image("cut.png"))
        self.window.tabs.setCurrentIndex(1)
        self.window._busy = True
        with patch("src.ui.main_window.QFileDialog.getSaveFileName",
                   return_value=(str(self.dir / "x.png"), "")) as dialog:
            self.window.save_current()
        self.assertFalse(dialog.called)

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

    def test_save_button_restored_after_operation(self) -> None:
        cut = self._image("cut.png", 4)
        with patch("src.ui.main_window.cut_task", return_value=str(cut)):
            self.window.source_path = IMAGE
            self.window.tb_cut.trigger()
            self.assertFalse(self.window.btn_save_current.isEnabled())
            self._finish()
        self.assertTrue(self.window.btn_save_current.isEnabled())

    def test_cut_activates_cutout_tab(self) -> None:
        cut = self._image("cut.png", 4)
        # Пользователь смотрит другую вкладку — после вырезки её нужно переключить.
        self.window.tabs.setCurrentIndex(0)
        self.assertEqual(self.window.tabs.tabText(self.window.tabs.currentIndex()), "Исходник")

        with patch("src.ui.main_window.cut_task", return_value=str(cut)):
            self.window.source_path = IMAGE
            self.window.tb_cut.trigger()
            self._finish()

        self.assertEqual(self.window.tabs.tabText(self.window.tabs.currentIndex()), "Вырезка")
        self.assertIsNotNone(self.window.previews["Вырезка"][0].source_pixmap())

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

    def test_generate_success_sets_background_and_switches_tab(self) -> None:
        background = self._image("generated.jpg")
        with patch("src.ui.main_window.genbg_task", return_value=str(background)):
            self.window.tb_generate.trigger()
            self._finish()
        self.assertEqual(self.window.background_path, background)
        self.assertIsNotNone(self.window.previews["Фон"][0].source_pixmap())
        self.assertEqual(self.window.tabs.tabText(self.window.tabs.currentIndex()), "Фон")

    def test_generate_task_panel_button_starts(self) -> None:
        background = self._image("panel.jpg")
        with patch("src.ui.main_window.genbg_task", return_value=str(background)):
            self.window.btn_generate.click()
            self.assertFalse(self.window.btn_generate.isEnabled())
            self._finish()
        self.assertTrue(self.window.btn_generate.isEnabled())
        self.assertEqual(self.window.background_path, background)

    def test_generate_without_prompt_does_not_start(self) -> None:
        self.window.prompt.clear()
        for button in (self.window.tb_generate, self.window.btn_generate):
            with self.subTest(button=button):
                if hasattr(button, "trigger"):
                    button.trigger()
                else:
                    button.click()
                self.assertIsNone(self.window._worker)
                self.assertIn("введите промпт", self.window.log_display.toPlainText())

    def test_settings_generate_button_applies_and_starts(self) -> None:
        background = self._image("from-settings.jpg")

        def exec_and_click(dialog):
            dialog.findChild(QPushButton, "settingsGenerate").click()
            return QDialog.DialogCode.Accepted

        with patch("src.ui.settings_dialog.SettingsDialog.exec", exec_and_click), \
             patch("src.ui.main_window.genbg_task", return_value=str(background)):
            self.window.open_settings()
            self._finish()
        self.assertEqual(self.window.background_path, background)
        self.assertEqual(self.window.tabs.tabText(self.window.tabs.currentIndex()), "Фон")

    def test_settings_show_provider_model_and_key_status(self) -> None:
        dialog = SettingsDialog(self.window)
        info = dialog.findChild(QLabel, "providerInfo")
        self.assertIn("Сейчас:", info.text())
        with patch("src.core.backgrounds.cf_creds", return_value=("account", "token")):
            dialog._update_provider_info()
        self.assertIn("Cloudflare", info.text())
        self.assertIn("flux-1-schnell", info.text())
        self.assertIn("ключ найден", info.text())
        combo = dialog.controls["bg/provider_api"]
        combo.setCurrentText("pollinations")
        self.assertIn("Pollinations", info.text())
        self.assertIn("ключ не нужен", info.text())

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
