"""Системная шапка диалогов: цвет должен совпадать с фоном окна."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.ui.native_titlebar import (
    _CAPTION_COLOR,
    _DARK_MODE,
    apply_dark_titlebar,
    colorref,
)


class TestColorref(unittest.TestCase):
    def test_hex_to_colorref(self) -> None:
        # COLORREF хранит каналы в порядке 0x00BBGGRR.
        self.assertEqual(colorref("#0f172a"), 0x002A170F)
        self.assertEqual(colorref("#f1f5f9"), 0x00F9F5F1)

    def test_invalid_color(self) -> None:
        with self.assertRaises(ValueError):
            colorref("abc")


class TestApplyDarkTitlebar(unittest.TestCase):
    @patch("src.ui.native_titlebar.sys.platform", "win32")
    @patch("src.ui.native_titlebar._set_attribute")
    def test_caption_is_painted_in_exact_theme_color(self, setter: MagicMock) -> None:
        widget = MagicMock()
        widget.winId.return_value = 1

        apply_dark_titlebar(widget, True, "#0f172a")

        self.assertEqual(setter.call_count, 2)
        dark_call, caption_call = setter.call_args_list
        self.assertEqual(dark_call.args[1], _DARK_MODE)
        self.assertEqual(caption_call.args[1], _CAPTION_COLOR)
        self.assertEqual(caption_call.args[2].value, 0x002A170F)

    @patch("src.ui.native_titlebar.sys.platform", "win32")
    @patch("src.ui.native_titlebar._set_attribute")
    def test_no_caption_call_without_color(self, setter: MagicMock) -> None:
        widget = MagicMock()
        widget.winId.return_value = 1

        apply_dark_titlebar(widget, False)

        setter.assert_called_once()
        self.assertEqual(setter.call_args.args[1], _DARK_MODE)


if __name__ == "__main__":
    unittest.main()
