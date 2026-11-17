"""Тесты чистых функций CLI-пайплайна (без сети и тяжёлых моделей)."""
from __future__ import annotations

import unittest

import numpy as np

from src import photo_pipeline as pp


class TestPipelineHelpers(unittest.TestCase):
    def test_crop_aspect_wider_image(self) -> None:
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        cropped = pp._crop_aspect(image, 1, 1)
        self.assertEqual(cropped.shape, (100, 100, 3))

    def test_crop_aspect_taller_image(self) -> None:
        image = np.zeros((200, 100, 3), dtype=np.uint8)
        cropped = pp._crop_aspect(image, 1, 1)
        self.assertEqual(cropped.shape, (100, 100, 3))

    def test_crop_aspect_keeps_nearly_matching_image(self) -> None:
        image = np.zeros((100, 101, 3), dtype=np.uint8)
        self.assertIs(pp._crop_aspect(image, 1, 1), image)

    def test_cover_returns_exact_size(self) -> None:
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        self.assertEqual(pp._cover(image, 50, 80).shape, (80, 50, 3))

    def test_levels_clips_to_range(self) -> None:
        values = np.array([-1.0, 0.0, 5.0, 10.0, 11.0])
        np.testing.assert_allclose(pp._levels(values, 0, 10), [0, 0, 0.5, 1, 1])

    def test_blur_keeps_shape(self) -> None:
        image = np.zeros((40, 60, 3), dtype=np.uint8)
        self.assertEqual(pp._blur(image, 1.5).shape, image.shape)

    def test_aspect_presets(self) -> None:
        cases = {
            (1920, 1080): "16:9",
            (1080, 1920): "9:16",
            (1024, 768): "4:3",
            (768, 1024): "3:4",
            (800, 800): "1:1",
        }
        for size, expected in cases.items():
            with self.subTest(size=size):
                self.assertEqual(pp._aspect(*size), expected)
