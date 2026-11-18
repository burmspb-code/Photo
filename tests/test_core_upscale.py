"""Апскейл ×2 (EDSR) и ×4 (Real-ESRGAN): выбор модели и кратность выхода."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.core.image import _read, _write
from src.core.settings import EDSR_X2_MODEL, ESR_MODEL, normalize_factor
from src.core.upscale import _run, _session, upscale


class FakeSession:
    def __init__(self, factor: int):
        self.factor = factor

    def get_inputs(self):
        return [SimpleNamespace(name="input")]

    def run(self, _outputs, feed):
        x = next(iter(feed.values()))
        h, w = x.shape[2:]
        return [np.zeros((1, 3, h * self.factor, w * self.factor), np.float32)]


class TestFactor(unittest.TestCase):
    def test_normalize_factor(self) -> None:
        self.assertEqual(normalize_factor(2), 2)
        self.assertEqual(normalize_factor("4"), 4)
        self.assertEqual(normalize_factor(3), 2)
        self.assertEqual(normalize_factor(None), 2)
        self.assertEqual(normalize_factor("мусор"), 2)

    def test_session_uses_edsr_for_2_and_esr_for_4(self) -> None:
        with patch("onnxruntime.InferenceSession") as session:
            _session(2)
            self.assertEqual(session.call_args.args[0], str(EDSR_X2_MODEL))
            _session(4)
            self.assertEqual(session.call_args.args[0], str(ESR_MODEL))

    def test_run_crops_padding_according_to_factor(self) -> None:
        img = np.full((30, 40, 3), 100, np.uint8)
        for factor in (2, 4):
            with self.subTest(factor=factor):
                out = _run(FakeSession(factor), img, factor)
                self.assertEqual(out.shape, (30 * factor, 40 * factor, 3))


class TestUpscaleOutput(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="photo-upscale-")
        self.dir = Path(self._tmp.name)
        self.src = self.dir / "src.jpg"
        _write(self.src, np.full((40, 60, 3), 128, np.uint8))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_factor_2_writes_half_size_output(self) -> None:
        out = self.dir / "out-2x.jpg"
        with patch("src.core.upscale._session", side_effect=lambda factor: FakeSession(factor)) as session:
            upscale(self.src, out, factor=2)
        session.assert_called_once_with(2)
        self.assertEqual(_read(out).shape[:2], (80, 120))

    def test_factor_4_writes_quarter_size_output(self) -> None:
        out = self.dir / "out-4x.jpg"
        with patch("src.core.upscale._session", side_effect=lambda factor: FakeSession(factor)) as session:
            upscale(self.src, out, factor=4)
        session.assert_called_once_with(4)
        self.assertEqual(_read(out).shape[:2], (160, 240))

    def test_default_factor_stays_4_for_internal_callers(self) -> None:
        out = self.dir / "out-default.jpg"
        with patch("src.core.upscale._session", side_effect=lambda factor: FakeSession(factor)):
            upscale(self.src, out)
        self.assertEqual(_read(out).shape[:2], (160, 240))

    def test_large_image_is_tiled_with_requested_factor(self) -> None:
        src = self.dir / "big.jpg"
        _write(src, np.full((800, 900, 3), 128, np.uint8))
        out = self.dir / "big-2x.jpg"
        with patch("src.core.upscale._session", side_effect=lambda factor: FakeSession(factor)):
            upscale(src, out, factor=2, tile=512, overlap=32)
        self.assertEqual(_read(out).shape[:2], (1600, 1800))


if __name__ == "__main__":
    unittest.main()
