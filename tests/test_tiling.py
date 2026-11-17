"""Сетка тайлов: полное покрытие кадра и обратная совместимость."""
from __future__ import annotations

import itertools
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src.core.cutout import cut_advisory, tiled_alpha, tiling_plan
from src.core.image import _write

TILE = 1024


class TestTilingPlan(unittest.TestCase):
    def test_legacy_two_tiles_for_approved_photo(self) -> None:
        """1632×1224 должна дать те же позиции, что и до правки."""
        self.assertEqual(tiling_plan(1224, 1632, TILE), ([0, 608], [0, 200]))

    def test_single_tile_for_small_image(self) -> None:
        self.assertEqual(tiling_plan(700, 900, TILE), ([0], [0]))

    def test_last_tile_is_flush_with_edge(self) -> None:
        xs, ys = tiling_plan(3456, 2592, TILE)
        self.assertEqual(xs[-1], 2592 - TILE)
        self.assertEqual(ys[-1], 3456 - TILE)

    def test_full_coverage_for_many_sizes(self) -> None:
        for h, w in ((1224, 1632), (2592, 3456), (2000, 2000), (4096, 2160),
                     (2049, 1025), (800, 5000), (500, 800)):
            with self.subTest(size=(h, w)):
                xs, ys = tiling_plan(h, w, TILE)
                covered = np.zeros((h, w), np.uint8)
                for y in ys:
                    for x in xs:
                        covered[y:y + TILE, x:x + TILE] = 1
                self.assertFalse((covered == 0).any(), f"дыры в {h}x{w}")

    def test_overlap_between_neighbouring_tiles(self) -> None:
        xs, _ = tiling_plan(3000, 3000, TILE)
        for prev, cur in itertools.pairwise(xs):
            self.assertLess(cur - prev, TILE, "соседние тайлы должны перекрываться")


class TestCutAdvisory(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="photo-advisory-")
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_high_contrast_small_image_has_no_notes(self) -> None:
        path = self.dir / "good.jpg"
        rng = np.random.default_rng(1)
        noise = rng.integers(0, 255, (600, 800, 3), dtype=np.uint8)
        _write(path, noise)
        self.assertEqual(cut_advisory(path), [])

    def test_low_contrast_is_flagged(self) -> None:
        path = self.dir / "flat.jpg"
        _write(path, np.full((600, 800, 3), 120, np.uint8))
        notes = cut_advisory(path)
        self.assertEqual(len(notes), 1)
        self.assertIn("Низкий контраст", notes[0])

    def test_large_image_is_flagged_with_tile_count(self) -> None:
        path = self.dir / "big.jpg"
        rng = np.random.default_rng(2)
        noise = rng.integers(0, 255, (1200, 2400, 3), dtype=np.uint8)
        _write(path, noise)
        notes = cut_advisory(path)
        self.assertEqual(len(notes), 1)
        self.assertIn("тайлами", notes[0])
        self.assertIn("2400×1200", notes[0])


class TestDegenerateTile(unittest.TestCase):
    def test_blank_tile_is_retried_with_context(self) -> None:
        """Тайл без объекта не должен заливать всю левую половину кадром."""
        img = np.full((1024, 2048, 3), 240, np.uint8)
        img[:, 1300:, :] = 10  # объект только в правой части
        calls: list[int] = []

        def fake_remove(buf, session=None, alpha_matting=False):
            calls.append(1)
            decoded = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
            if len(calls) == 1:
                alpha = np.full(decoded.shape[:2], 255, np.uint8)  # сбой модели
            else:
                alpha = np.zeros(decoded.shape[:2], np.uint8)
                alpha[:, decoded.shape[1] // 2:] = 255  # контекст дал маску
            rgba = cv2.cvtColor(decoded, cv2.COLOR_BGR2BGRA)
            rgba[:, :, 3] = alpha
            return cv2.imencode(".png", rgba)[1].tobytes()

        with patch("src.core.cutout.get_session", return_value=object()), \
             patch("src.core.cutout.remove", side_effect=fake_remove):
            alpha = tiled_alpha(img)

        self.assertEqual(len(calls), 3)  # 2 тайла + 1 повтор с контекстом
        self.assertLess(float(alpha[:, :1024].mean()), 0.9)
        self.assertGreater(float(alpha[:, 1600:].mean()), 0.3)


if __name__ == "__main__":
    unittest.main()
