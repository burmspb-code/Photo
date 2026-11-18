"""Контекстные подсказки в нижнем инфоокне: один совет на состояние задачи."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from src.core.image import _write
from src.ui.main_window import MainWindow
from tests.gui_case import GuiTestCase, app_settings


class TestInfoHints(GuiTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="photo-info-hints-")
        self.dir = Path(self._tmp.name)
        stored = app_settings()
        stored.remove("upscale/factor")
        stored.remove("ui/hints")
        stored.sync()
        self.window = MainWindow()
        self.window.show()
        self.process_events()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.process_events()
        self._tmp.cleanup()

    def _image(self, name: str, width: int = 120, height: int = 90) -> Path:
        path = self.dir / name
        _write(path, np.full((height, width, 3), 128, np.uint8))
        return path

    def hints(self) -> list[str]:
        lines = self.window.log_display.toPlainText().splitlines()
        return [line for line in lines if "[HINT]" in line]

    def last_hint(self) -> str:
        return self.hints()[-1]

    def _ready(self, source_size=(1632, 1224), bg_size=(1024, 768)) -> tuple[Path, Path]:
        source = self._image("source.jpg", *source_size)
        cut = self._image("cutout.png", *source_size)
        self.window.source_path = source
        self.window.previews["Вырезка"][0].set_image(cut)
        self.window._cut_source_path = source
        background = self._image("park.jpg", *bg_size)
        self.window._set_background(background)
        return cut, background

    def test_start_hint_asks_to_open_source(self) -> None:
        self.assertIn("Откройте исходное фото", self.last_hint())

    def test_hint_follows_source_and_cut(self) -> None:
        source = self._image("source.jpg")
        self.window.source_path = source
        self.window._update_hint()
        self.assertIn("Вырежьте объект", self.last_hint())

        self.window._on_operation_success("Вырезка", self._image("cutout.png"))
        self.assertEqual(self.window._cut_source_path, source)
        self.assertIn("Выберите готовый фон", self.last_hint())

    def test_small_background_recommends_upscale_with_both_resolutions(self) -> None:
        self._ready()
        hint = self.last_hint()
        self.assertIn("1024×768", hint)
        self.assertIn("1632×1224", hint)
        self.assertIn("апскейл ×2", hint)
        self.assertIn("останется 1632×1224", hint)

    def test_upscale_factor_from_settings_is_used_in_hint(self) -> None:
        self.window.settings.setValue("upscale/factor", 4)
        self._ready()
        self.assertIn("апскейл ×4", self.last_hint())

    def test_large_background_says_upscale_is_not_needed(self) -> None:
        self._ready(bg_size=(2048, 1536))
        hint = self.last_hint()
        self.assertIn("2048×1536", hint)
        self.assertIn("апскейл не нужен", hint)
        self.assertIn("собирайте композит", hint)

    def test_hint_is_not_logged_twice_for_same_state(self) -> None:
        self._ready()
        count = len(self.hints())
        self.window._update_hint()
        self.window._update_hint()
        self.assertEqual(len(self.hints()), count)

    def test_changed_source_after_cut_advises_to_recut(self) -> None:
        self._ready()
        self.window.source_path = self._image("new-source.jpg")
        self.window._update_hint()
        self.assertIn("повторите вырезку", self.last_hint())

    def test_changed_background_after_compose_advises_to_recompose(self) -> None:
        _cut, background = self._ready()
        result = self._image("result.jpg")
        self.window._on_operation_success("Сборка композита", result)
        self.assertEqual(self.window._composed_bg_path, background)
        self.assertIn("Результат готов", self.last_hint())

        self.window._set_background(self._image("new-park.jpg", 2048, 1536))
        self.assertIn("соберите композит заново", self.last_hint())

    def test_hints_can_be_disabled_and_reenabled(self) -> None:
        self.window.settings.setValue("ui/hints", False)
        self.window._update_hint()
        count = len(self.hints())

        self._ready()
        self.assertEqual(len(self.hints()), count)

        self.window.settings.setValue("ui/hints", True)
        self.window._update_hint()
        self.assertIn("апскейл ×2", self.last_hint())

    def test_compose_without_cut_does_not_use_stale_file(self) -> None:
        self.window.source_path = self._image("source.jpg")
        self.window._set_background(self._image("park.jpg"))
        stale = self.dir / "cutout.png"
        _write(stale, np.zeros((8, 10, 4), np.uint8))
        self.assertTrue(stale.exists())

        self.window.tb_compose.trigger()

        self.assertIsNone(self.window._worker)
        hint = self.last_hint()
        self.assertIn("не хватает вырезки", hint)
        self.assertIn("вырежьте объект", hint)

    def test_compose_with_cut_from_other_source_is_blocked(self) -> None:
        old_source = self._image("old-source.jpg")
        self.window.source_path = old_source
        self.window.previews["Вырезка"][0].set_image(self._image("cutout.png"))
        self.window._cut_source_path = old_source
        self.window._set_background(self._image("park.jpg"))
        self.window.source_path = self._image("new-source.jpg")

        self.window.tb_compose.trigger()

        self.assertIsNone(self.window._worker)
        self.assertIn("повторите вырезку", self.last_hint())

    def test_blocked_compose_reports_warn_when_hints_disabled(self) -> None:
        self.window.settings.setValue("ui/hints", False)
        self.window.source_path = self._image("source.jpg")
        self.window._set_background(self._image("park.jpg"))
        before = len(self.hints())

        self.window.tb_compose.trigger()

        logs = self.window.log_display.toPlainText()
        self.assertIsNone(self.window._worker)
        self.assertEqual(len(self.hints()), before)
        self.assertIn("[WARN]", logs)
        self.assertIn("вырежьте объект", logs)

    def test_no_hint_is_written_while_busy(self) -> None:
        count = len(self.hints())
        self.window._set_busy(True)
        self.assertEqual(len(self.hints()), count)
        self.window._set_busy(False)
        self.assertEqual(len(self.hints()), count)
