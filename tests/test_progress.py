"""Тесты примитивов прогресса и отмены."""
from __future__ import annotations

import unittest

from src.core.progress import CancelledError, check_cancel, scaled, sleep_or_cancel


class TestProgress(unittest.TestCase):
    def test_scaled_maps_range(self) -> None:
        reports = []
        callback = scaled(lambda p, m: reports.append((p, m)), 10, 90)
        assert callback is not None
        callback(0, "start")
        callback(50, "half")
        callback(100, "end")
        callback(-1, "unknown")
        self.assertEqual(reports, [(10, "start"), (50, "half"), (90, "end"), (-1, "unknown")])

    def test_scaled_without_callback(self) -> None:
        self.assertIsNone(scaled(None, 10, 90))

    def test_check_cancel(self) -> None:
        check_cancel(None)
        check_cancel(lambda: False)
        with self.assertRaises(CancelledError):
            check_cancel(lambda: True)

    def test_sleep_or_cancel_is_interruptible(self) -> None:
        sleep_or_cancel(0.01, None)
        with self.assertRaises(CancelledError):
            sleep_or_cancel(30, lambda: True)
