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


def theme_is_dark(parent: Any | None) -> bool:
    """Тема родителя: по умолчанию тёмная, как и у главного окна."""
    return getattr(parent, "_theme_name", "Тёмная") != "Светлая"


def _set_attribute(hwnd: Any, attribute: int, value: ctypes.c_int) -> bool:
    """Выставить атрибут DWM; старые версии Windows могут не знать атрибут."""
    try:
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:  # API есть не во всех версиях Windows
        return False
    return result == 0


def apply_dark_titlebar(widget: Any, dark: bool) -> None:
    """Включить/выключить тёмную системную шапку у нативного окна виджета."""
    if sys.platform != "win32":
        return
    value = ctypes.c_int(1 if dark else 0)
    hwnd = wintypes.HWND(int(widget.winId()))
    for attribute in (_DARK_MODE, _DARK_MODE_LEGACY):
        if _set_attribute(hwnd, attribute, value):
            return
