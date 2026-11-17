"""Тесты задач GUI: файлы, параметры и передача прогресса в ядро."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src.core import tasks
from src.core.image import _write


class TestTasks(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="photo-tasks-")
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cut_task_writes_rgba_and_forwards_options(self) -> None:
        calls = {}
        progress = []

        def fake_make(src, **kwargs):
            calls.update(kwargs)
            kwargs["progress"](50, "половина")
            return np.full((6, 5, 4), 128, np.uint8)

        out = self.dir / "cut.png"
        with patch("src.core.cutout.make_cutout", side_effect=fake_make):
            result = tasks.cut_task(
                "in.jpg", out,
                options={"portrait": False, "model": "u2net", "tile": 512,
                         "sigma": 2.0, "head_ratio": 0.5, "matting": False},
                progress=lambda p, m: progress.append((p, m)),
            )

        self.assertEqual(result, str(out))
        self.assertEqual(cv2.imread(str(out), cv2.IMREAD_UNCHANGED).shape, (6, 5, 4))
        self.assertFalse(calls["portrait"])
        self.assertEqual(calls["model"], "u2net")
        self.assertEqual(calls["tile"], 512)
        self.assertEqual(calls["sigma"], 2.0)
        self.assertEqual(calls["head_ratio"], 0.5)
        self.assertFalse(calls["matting"])
        self.assertTrue(any(message == "половина" for _p, message in progress))

    def test_genbg_task_adds_required_prompt_and_options(self) -> None:
        with patch("src.core.prompt.translate_to_english", return_value="park"), \
             patch("src.core.backgrounds.genbg") as genbg:
            out = self.dir / "bg.jpg"
            result = tasks.genbg_task(
                "парк в 2К", out,
                options={"provider": "cloudflare", "seed": 3, "size": "2K"},
            )

        self.assertEqual(result, str(out))
        args, kwargs = genbg.call_args
        self.assertEqual(args[0], "park, realistic photo, no people, no text")
        self.assertEqual(args[1], str(out))
        self.assertEqual(kwargs["provider"], "cloudflare")
        self.assertEqual(kwargs["seed"], 3)
        self.assertEqual(kwargs["size"], "2K")

    def test_genbg_task_translates_russian_and_reports_it(self) -> None:
        progress = []
        with patch("src.core.prompt.translate_to_english", return_value="rocky arctic shore"), \
             patch("src.core.backgrounds.genbg") as genbg:
            tasks.genbg_task(
                "Скалистый берег Северного ледовитого океана", self.dir / "bg.jpg",
                progress=lambda p, m: progress.append((p, m)),
            )

        self.assertEqual(genbg.call_args.args[0],
                         "rocky arctic shore, realistic photo, no people, no text")
        self.assertTrue(any("Перевод" in message for _p, message in progress))

    def test_genbg_task_warns_when_translation_fails(self) -> None:
        progress = []
        with patch("src.core.prompt.translate_to_english", side_effect=lambda t: t), \
             patch("src.core.backgrounds.genbg"):
            tasks.genbg_task(
                "скалистый берег", self.dir / "bg.jpg",
                progress=lambda p, m: progress.append((p, m)),
            )
        self.assertTrue(any("Перевод недоступен" in message for _p, message in progress))

    def test_genbg_task_keeps_compliant_prompt(self) -> None:
        prompt = "realistic photo, no people, no text, soft light"
        with patch("src.core.backgrounds.genbg") as genbg:
            tasks.genbg_task(prompt, self.dir / "bg.jpg")
        self.assertEqual(genbg.call_args.args[0], prompt)

    def test_upscale_task_default_name(self) -> None:
        with patch("src.core.upscale.upscale") as upscale:
            result = tasks.upscale_task(self.dir / "photo.jpg")
        self.assertEqual(Path(result).name, "photo-4x.jpg")
        self.assertEqual(upscale.call_args.args[1], result)

    def test_upscale_task_removes_old_4x_suffix(self) -> None:
        with patch("src.core.upscale.upscale") as upscale:
            result = tasks.upscale_task(self.dir / "photo-4x.jpg")
        self.assertEqual(Path(result).name, "photo-4x.jpg")
        self.assertEqual(upscale.call_args.args[0], self.dir / "photo-4x.jpg")

    def test_compose_task_rejects_image_without_alpha(self) -> None:
        cut = self.dir / "cut.png"
        bg = self.dir / "bg.jpg"
        _write(cut, np.zeros((4, 4, 3), np.uint8))
        _write(bg, np.zeros((4, 4, 3), np.uint8))
        with self.assertRaisesRegex(ValueError, "альфа"):
            tasks.compose_task(cut, bg, self.dir / "result.jpg")

    def test_compose_task_writes_result_and_forwards_options(self) -> None:
        cut = self.dir / "cut.png"
        bg = self.dir / "bg.jpg"
        _write(cut, np.zeros((4, 4, 4), np.uint8))
        _write(bg, np.zeros((4, 4, 3), np.uint8))
        out = self.dir / "result.jpg"
        with patch("src.core.compose.composite", return_value=np.zeros((4, 4, 3), np.uint8)) as composite:
            result = tasks.compose_task(
                cut, bg, out,
                options={"blur": 0.5, "shadow": 0.2, "tone": 1.1, "grain": 3.0, "seed": 42},
            )
        self.assertEqual(result, str(out))
        self.assertTrue(out.exists())
        kwargs = composite.call_args.kwargs
        self.assertEqual(kwargs["blur_bg"], 0.5)
        self.assertEqual(kwargs["shadow"], 0.2)
        self.assertEqual(kwargs["tone"], 1.1)
        self.assertEqual(kwargs["grain"], 3.0)
        self.assertEqual(kwargs["seed"], 42)
