"""Оформление нативной строки заголовка Windows в цвете темы приложения.

QSS красит содержимое QDialog, но не системную шапку: без DWM-атрибута она
остаётся светлой, и в тёмной теме окно выглядит собранным из двух разных тем.
Атрибут выставляется на HWND диалога; на не-Windows платформах вызов просто
ничего не делает.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any

# DWMWA_USE_IMMERSIVE_DARK_MODE: 20 в актуальных версиях, 19 в старых Windows 10.
_DARK_MODE = 20
_DARK_MODE_LEGACY = 19
# DWMWA_CAPTION_COLOR (Windows 11 22H2+): красит шапку в точный COLORREF.
# Одноimmersive dark mode даёт серый #1c212c, который не совпадает с фоном
# приложения (#0f172a), поэтому шапка выглядит чужой.
_CAPTION_COLOR = 35


def theme_is_dark(parent: Any | None) -> bool:
    """Тема родителя: по умолчанию тёмная, как и у главного окна."""
    return getattr(parent, "_theme_name", "Тёмная") != "Светлая"


def colorref(hex_color: str) -> int:
    """Преобразовать '#0f172a' в COLORREF Windows (0x00BBGGRR)."""
    text = hex_color.lstrip("#")
    if len(text) != 6:
        raise ValueError(f"Ожидался цвет вида #RRGGBB, получено: {hex_color!r}")
    red, green, blue = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    return (blue << 16) | (green << 8) | red


def _set_attribute(hwnd: Any, attribute: int, value: Any) -> bool:
    """Выставить атрибут DWM; старые версии Windows могут не знать атрибут."""
    try:
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:  # API есть не во всех версиях Windows
        return False
    return result == 0


def apply_dark_titlebar(
    widget: Any, dark: bool, caption_color: str | None = None
) -> None:
    """Оформить системную шапку окна под тему приложения.

    ``caption_color`` — точный цвет фона окна из палитры темы; если задан,
    шапка красится в него через DWMWA_CAPTION_COLOR и не отличается от фона
    диалога. На старых Windows атрибут просто не подействует.
    """
    if sys.platform != "win32":
        return
    hwnd = wintypes.HWND(int(widget.winId()))
    value = ctypes.c_int(1 if dark else 0)
    for attribute in (_DARK_MODE, _DARK_MODE_LEGACY):
        if _set_attribute(hwnd, attribute, value):
            break
    if caption_color:
        _set_attribute(hwnd, _CAPTION_COLOR, ctypes.c_uint32(colorref(caption_color)))
