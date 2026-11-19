"""Удаление мелких обособленных элементов из альфы."""
from __future__ import annotations

import unittest

import numpy as np

from src.core.cutout import clean_color_gaps, fill_holes, refine_hair, remove_isolated


class TestRemoveIsolated(unittest.TestCase):
    @staticmethod
    def _canvas(size=200):
        alpha = np.zeros((size, size), np.float32)
        alpha[20:160, 20:160] = 1.0  # основной силуэт
        return alpha

    def test_small_remote_fragment_is_removed(self) -> None:
        alpha = self._canvas()
        alpha[185:195, 185:195] = 1.0  # далеко от силуэта

        out = remove_isolated(alpha)

        self.assertEqual(float(out[190, 190]), 0.0)
        self.assertEqual(float(out[100, 100]), 1.0)
        self.assertLess(float(out[175, 190]), 0.05)  # мягкая кромка тоже убрана

    def test_large_remote_fragment_is_kept(self) -> None:
        alpha = self._canvas(400)
        alpha[250:350, 250:350] = 1.0  # крупный фрагмент — может быть частью объекта

        out = remove_isolated(alpha)

        self.assertEqual(float(out[300, 300]), 1.0)

    def test_small_but_close_fragment_is_kept(self) -> None:
        alpha = self._canvas()
        alpha[163:173, 100:110] = 1.0  # зазор 3 px — деталь силуэта

        out = remove_isolated(alpha)

        self.assertEqual(float(out[168, 105]), 1.0)

    def test_clean_alpha_is_returned_unchanged(self) -> None:
        alpha = self._canvas()

        out = remove_isolated(alpha)

        self.assertIs(out, alpha)

    def test_custom_thresholds(self) -> None:
        alpha = self._canvas()
        alpha[185:195, 185:195] = 1.0

        self.assertEqual(float(remove_isolated(alpha, min_ratio=0.001)[190, 190]), 1.0)
        self.assertEqual(float(remove_isolated(alpha, min_gap=100)[190, 190]), 1.0)

    def test_soft_edge_of_fragment_is_zeroed(self) -> None:
        alpha = self._canvas()
        alpha[180:200, 180:200] = 0.6  # полупрозрачный ореол вокруг фрагмента
        alpha[185:195, 185:195] = 1.0

        out = remove_isolated(alpha)

        self.assertEqual(float(out[183, 190]), 0.0)
        self.assertEqual(float(out[100, 100]), 1.0)

    def test_custom_halo_wipes_wider_fringe(self) -> None:
        alpha = self._canvas()
        alpha[180:200, 180:200] = 0.6
        alpha[185:195, 185:195] = 1.0

        out = remove_isolated(alpha, halo=32)

        self.assertEqual(float(out[175, 190]), 0.0)
        self.assertEqual(float(out[100, 100]), 1.0)


class TestFillHoles(unittest.TestCase):
    @staticmethod
    def _canvas(size=200):
        alpha = np.zeros((size, size), np.float32)
        alpha[20:180, 20:180] = 1.0
        return alpha

    def test_small_upper_hole_is_filled(self) -> None:
        alpha = self._canvas()
        alpha[35:55, 60:90] = 0.0

        out = fill_holes(alpha)

        self.assertGreater(float(out[45, 75]), 0.9)
        self.assertEqual(float(out[100, 100]), 1.0)

    def test_large_and_lower_holes_are_kept(self) -> None:
        alpha = self._canvas()
        alpha[35:95, 60:160] = 0.0   # площадь 6000 — крупная пустота
        alpha[120:140, 60:90] = 0.0  # нижняя часть силуэта

        out = fill_holes(alpha, max_area=5000)

        self.assertEqual(float(out[50, 100]), 0.0)
        self.assertEqual(float(out[130, 75]), 0.0)

    def test_tiny_upper_holes_are_kept(self) -> None:
        alpha = self._canvas()
        alpha[35:45, 60:75] = 0.0  # 150 px — деталь силуэта

        out = fill_holes(alpha)

        self.assertEqual(float(out[40, 67]), 0.0)

    def test_hole_larger_than_limit_is_kept(self) -> None:
        alpha = self._canvas(400)
        alpha[40:150, 40:150] = 0.0  # 12100 px

        out = fill_holes(alpha, max_area=5000)

        self.assertEqual(float(out[90, 90]), 0.0)

    def test_large_upper_hole_is_filled_by_default(self) -> None:
        alpha = self._canvas(400)
        alpha[40:150, 40:150] = 0.0  # 12100 px < 60000

        out = fill_holes(alpha)

        self.assertGreater(float(out[90, 90]), 0.9)

    def test_clean_alpha_is_returned_unchanged(self) -> None:
        alpha = self._canvas()

        self.assertIs(fill_holes(alpha), alpha)


class TestRefineHair(unittest.TestCase):
    @staticmethod
    def _canvas(size=200):
        alpha = np.zeros((size, size), np.float32)
        alpha[20:180, 20:180] = 1.0
        return alpha

    def test_dense_fringe_is_boosted(self) -> None:
        alpha = self._canvas()
        alpha[30:50, 30:150] = 0.3  # 2400 px каймы в верхней доле силуэта

        out = refine_hair(alpha, min_mid=1000, gain=2.0)

        self.assertAlmostEqual(float(out[40, 90]), 0.6, places=5)
        self.assertEqual(float(out[100, 90]), 1.0)  # ядро не тронуто
        self.assertEqual(float(out[10, 10]), 0.0)   # фон не тронут

    def test_small_fringe_below_threshold_is_unchanged(self) -> None:
        alpha = self._canvas()
        alpha[30:50, 30:150] = 0.3

        self.assertIs(refine_hair(alpha), alpha)

    def test_clean_alpha_is_returned_unchanged(self) -> None:
        alpha = self._canvas()

        self.assertIs(refine_hair(alpha), alpha)

    def test_bottom_of_region_fades_without_hard_seam(self) -> None:
        alpha = self._canvas()
        alpha[30:59, 30:150] = 0.3

        out = refine_hair(alpha, min_mid=1000, gain=2.0)

        self.assertAlmostEqual(float(out[32, 90]), 0.6, places=5)
        self.assertLess(float(out[58, 90]), float(out[32, 90]))
        self.assertGreater(float(out[58, 90]), 0.3)


class TestCleanColorGaps(unittest.TestCase):
    @staticmethod
    def _scene(bg):
        orig = np.zeros((200, 200, 3), np.uint8)
        orig[:] = bg
        alpha = np.zeros((200, 200), np.float32)
        alpha[20:180, 20:180] = 1.0
        cut = np.dstack([orig, (alpha * 255).astype(np.uint8)])
        return orig, cut

    def test_blue_gap_inside_head_becomes_transparent(self) -> None:
        orig, cut = self._scene((228, 213, 173))  # RGB (173,213,228) — светло-голубой
        orig[30:50, 30:150] = (225, 212, 178)     # почти точный фон между прядями
        cut[:, :, :3] = orig

        out = clean_color_gaps(orig, cut)

        self.assertLess(float(out[40, 90, 3]), 10)
        self.assertEqual(float(out[100, 90, 3]), 255)  # ниже зоны — без изменений
        self.assertEqual(float(out[10, 10, 3]), 0)     # внешний фон — без изменений
        np.testing.assert_array_equal(out[:, :, :3], cut[:, :, :3])  # цвет не тронут

    def test_warm_background_is_untouched(self) -> None:
        orig, cut = self._scene((60, 64, 69))  # B-R = 9 — не голубой
        orig[30:50, 30:150] = (61, 64, 69)
        cut[:, :, :3] = orig

        self.assertIs(clean_color_gaps(orig, cut), cut)

    def test_color_far_from_background_keeps_alpha(self) -> None:
        orig, cut = self._scene((228, 213, 173))
        orig[30:50, 30:150] = (81, 96, 114)       # тёмные волосы

        out = clean_color_gaps(orig, cut)

        self.assertEqual(float(out[40, 90, 3]), 255)


if __name__ == "__main__":
    unittest.main()
