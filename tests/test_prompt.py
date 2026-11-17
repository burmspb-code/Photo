"""Тесты подготовки промпта и пресетов размера фона."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src.core.backgrounds import _fit_size
from src.core.image import _write
from src.core.prompt import (
    has_cyrillic,
    prepare_prompt,
    strip_resolution,
    translate_to_english,
)
from src.core.sizes import SIZE_ORDER, size_for


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TestPrompt(unittest.TestCase):
    def test_has_cyrillic(self) -> None:
        self.assertTrue(has_cyrillic("Скалистый берег"))
        self.assertTrue(has_cyrillic("ёлка"))
        self.assertFalse(has_cyrillic("Rocky coast"))
        self.assertFalse(has_cyrillic(""))

    def test_strip_resolution_removes_russian_and_english(self) -> None:
        self.assertEqual(strip_resolution("сделай фото в 2К - берег"), "сделай фото, берег")
        self.assertEqual(strip_resolution("coast in 4k, overcast"), "coast, overcast")
        self.assertEqual(strip_resolution("фото 2160p, море"), "фото 2160p, море")

    def test_translate_parses_google_response(self) -> None:
        payload = [[["rocky coast", "скалистый берег", None, None, 10]], None, "ru"]
        with patch("src.core.prompt.urllib.request.urlopen", return_value=_Response(payload)):
            result = translate_to_english("скалистый берег")
        self.assertEqual(result, "rocky coast")

    def test_translate_falls_back_on_network_error(self) -> None:
        with patch("src.core.prompt.urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertEqual(translate_to_english("скалистый берег"), "скалистый берег")

    def test_translate_skips_english(self) -> None:
        with patch("src.core.prompt.urllib.request.urlopen") as urlopen:
            self.assertEqual(translate_to_english("rocky coast"), "rocky coast")
        urlopen.assert_not_called()

    def test_prepare_prompt_translates_and_deduplicates(self) -> None:
        with patch("src.core.prompt.translate_to_english",
                   return_value="take a realistic photo, rocky coast"):
            result = prepare_prompt("реалистичное фото в 2К - скалистый берег")
        self.assertEqual(result, "take a realistic photo, rocky coast, no people, no text")

    def test_prepare_prompt_appends_missing_parts_only(self) -> None:
        self.assertEqual(
            prepare_prompt("rocky coast, no people"),
            "rocky coast, no people, realistic photo, no text",
        )

    def test_prepare_prompt_empty(self) -> None:
        self.assertEqual(prepare_prompt(""), "realistic photo, no people, no text")


class TestSizes(unittest.TestCase):
    def test_presets(self) -> None:
        self.assertEqual(SIZE_ORDER, ("1K", "2K", "4K"))
        self.assertEqual(size_for("1K"), (1024, 768))
        self.assertEqual(size_for("2k"), (2048, 1536))
        self.assertEqual(size_for("4K"), (4096, 3072))
        self.assertIsNone(size_for(None))
        self.assertIsNone(size_for("8K"))

    def test_fit_size_resizes_exactly_without_esrgan(self) -> None:
        with tempfile.TemporaryDirectory(prefix="photo-sizes-") as tmp:
            path = Path(tmp) / "bg.jpg"
            _write(path, np.zeros((8, 10, 3), np.uint8))
            with patch("src.core.backgrounds.ESR_MODEL") as esr_model:
                esr_model.exists.return_value = False
                _fit_size(path, 4, 3)
            self.assertEqual(cv2.imread(str(path)).shape[:2], (3, 4))


if __name__ == "__main__":
    unittest.main()
