"""Цельный кадр как страховка для тайловой вырезки."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import cv2
import numpy as np

from src.core.cutout import global_shape_alpha, merge_global_shape, stabilize_alpha


class TestGlobalShapeAlpha(unittest.TestCase):
    def test_alpha_stretch_and_hard_limits(self) -> None:
        orig = np.zeros((40, 40, 3), np.uint8)
        alpha = np.zeros((40, 40), np.uint8)
        alpha[0:10, :] = 8
        alpha[10:20, :] = 247
        alpha[20:30, :] = 255
        rgba = np.dstack([orig, alpha])
        raw = cv2.imencode(".png", rgba)[1].tobytes()

        with patch("src.core.cutout.get_session", return_value=object()), \
             patch("src.core.cutout.remove", return_value=raw):
            out = global_shape_alpha(orig)

        self.assertEqual(float(out[5, 20]), 0.0)
        self.assertEqual(float(out[15, 20]), 1.0)
        self.assertEqual(float(out[25, 20]), 1.0)
        self.assertEqual(float(out[35, 20]), 0.0)


class TestMergeGlobalShape(unittest.TestCase):
    def test_fills_area_found_on_whole_frame(self) -> None:
        alpha = np.zeros((200, 200), np.float32)
        alpha[10:190, 10:190] = 1.0
        alpha[60:130, 60:130] = 0.2  # пропуск внутри объекта
        whole = np.zeros_like(alpha)
        whole[10:190, 10:190] = 1.0

        out = merge_global_shape(alpha, whole)

        self.assertGreater(float(out[95, 95]), 0.95)
        self.assertGreater(float(out[30, 30]), 0.95)
        self.assertEqual(float(out[5, 5]), 0.0)

    def test_small_disagreement_is_ignored(self) -> None:
        alpha = np.zeros((200, 200), np.float32)
        alpha[10:190, 10:190] = 1.0
        alpha[100:103, 100:103] = 0.2  # 9 px — заведомо меньше порога 0,1 %
        whole = np.zeros_like(alpha)
        whole[10:190, 10:190] = 1.0

        out = merge_global_shape(alpha, whole)

        np.testing.assert_array_equal(out, alpha)

    def test_does_not_add_where_whole_frame_is_transparent(self) -> None:
        alpha = np.zeros((100, 100), np.float32)
        whole = np.zeros_like(alpha)
        whole[20:80, 20:80] = 0.3  # ниже порога уверенности 0,9

        out = merge_global_shape(alpha, whole)

        np.testing.assert_array_equal(out, alpha)


class TestStabilizeAlpha(unittest.TestCase):
    def test_clean_alpha_is_not_touched(self) -> None:
        alpha = np.zeros((100, 100), np.float32)
        alpha[10:90, 10:90] = 1.0
        alpha[40:44, 40:44] = 0.6  # 1,3 % кадра — ниже порога 3 %

        out = stabilize_alpha(alpha)

        np.testing.assert_array_equal(out, alpha)

    def test_speckled_background_is_removed(self) -> None:
        alpha = np.zeros((300, 300), np.float32)
        alpha[100:200, 100:200] = 1.0
        alpha[::5, ::5] = 0.6  # мелкие островки вне объекта

        out = stabilize_alpha(alpha)

        self.assertEqual(float(out[10, 10]), 0.0)
        self.assertEqual(float(out[150, 150]), 1.0)
        self.assertLess(float(((out > 0.05) & (out < 0.95)).mean()), 0.05)

    def test_gap_inside_silhouette_becomes_opaque(self) -> None:
        alpha = np.zeros((200, 200), np.float32)
        alpha[20:180, 20:180] = 1.0
        alpha[80:130, 80:140] = 0.6  # 5 % кадра, одна компонента

        out = stabilize_alpha(alpha)

        self.assertEqual(float(out[100, 100]), 1.0)
        self.assertEqual(float(out[30, 30]), 1.0)
        self.assertEqual(float(out[5, 5]), 0.0)


if __name__ == "__main__":
    unittest.main()
