"""Тесты чистых хелперов GUI: иконки и таблица краёв окна."""
from __future__ import annotations

from collections import Counter

from PyQt6.QtGui import QColor

from src.ui.defaults import CUT_MODEL_HINTS
from src.ui.main_window import (
    CUT_MODELS,
    LEVEL_COLORS,
    PREVIEW_TABS,
    _HT_EDGES,
    _icon,
    _solid_icon,
)
from tests.gui_case import GuiTestCase


def dominant_color(icon, size: int = 32) -> str:
    """Основной непрозрачный цвет иконки — удобно проверять перекрашивание."""
    image = icon.pixmap(size, size).toImage()
    counts: Counter[str] = Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            color = QColor(image.pixelColor(x, y))
            if color.alpha() > 128:
                counts[color.name()] += 1
    return counts.most_common(1)[0][0] if counts else ""


class TestIcons(GuiTestCase):
    STANDARD_NAMES = (
        "SP_DialogOpenButton",
        "SP_MediaPlay",
        "SP_BrowserReload",
        "SP_ArrowUp",
        "SP_DialogApplyButton",
        "SP_BrowserStop",
        "SP_DialogSaveButton",
    )

    def test_standard_icons_exist(self) -> None:
        for name in self.STANDARD_NAMES:
            with self.subTest(name=name):
                self.assertFalse(_icon(name).isNull())

    def test_unknown_icon_is_empty(self) -> None:
        self.assertTrue(_icon("SP_NoSuchPixmap").isNull())

    def test_solid_icon_keeps_shape_and_uses_color(self) -> None:
        icon = _solid_icon("SP_MediaPlay", "#16a34a")
        self.assertFalse(icon.isNull())
        self.assertEqual(dominant_color(icon), "#16a34a")
        # Фигура сохраняется: зелёных пикселей заметно больше нуля, но не весь квадрат.
        image = icon.pixmap(32, 32).toImage()
        filled = sum(
            1 for y in range(32) for x in range(32)
            if QColor(image.pixelColor(x, y)).alpha() > 128
        )
        self.assertGreater(filled, 50)
        self.assertLess(filled, 32 * 32)


class TestWindowEdges(GuiTestCase):
    def test_edge_codes(self) -> None:
        # HTLEFT/HTRIGHT/HTTOP/HTBOTTOM и четыре угла (Windows WM_NCHITTEST).
        expected = {
            (-1, 0): 10,
            (1, 0): 11,
            (0, -1): 12,
            (0, 1): 15,
            (-1, -1): 13,
            (1, -1): 14,
            (-1, 1): 16,
            (1, 1): 17,
        }
        self.assertEqual(_HT_EDGES, expected)

    def test_center_is_not_an_edge(self) -> None:
        self.assertNotIn((0, 0), _HT_EDGES)


class TestConstants(GuiTestCase):
    def test_preview_tabs(self) -> None:
        self.assertEqual(
            PREVIEW_TABS,
            ("Исходник", "Вырезка", "Фон", "Результат", "До — После"),
        )

    def test_cut_models(self) -> None:
        """Только проверенные модели: две BiRefNet, ISNet и u2netp для превью."""
        self.assertEqual(
            CUT_MODELS,
            ("birefnet-general", "birefnet-portrait", "isnet-general-use", "u2netp"),
        )
        for removed in ("birefnet-general-lite", "birefnet-general-fp16",
                        "birefnet-massive", "u2net"):
            self.assertNotIn(removed, CUT_MODELS)
        self.assertEqual(set(CUT_MODEL_HINTS), set(CUT_MODELS))

    def test_log_levels(self) -> None:
        self.assertEqual(set(LEVEL_COLORS), {"OK", "HINT", "INFO", "WARN", "ERROR"})
