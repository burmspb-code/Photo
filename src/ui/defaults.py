"""Проверенные предустановки приложения (утверждённый результат C, 2026-11-17).

Значения выбраны по карточке результата и командам, которые дали нужные
вырезку и композит. ``apply_default_presets`` вызывается при запуске GUI:
он однократно исправляет устаревшие ключи (например, ``cut/model = u2netp``),
но не перетирает пользовательские изменения после своей первой записи.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings

# Поднимать при изменении набора предустановок — заставит применить их заново.
DEFAULTS_VERSION = 1

APP_DEFAULTS: dict[str, object] = {
    # Вырезка: параметры команды `cut` из карточки результата C.
    "cut/model": "birefnet-general",
    "cut/portrait": True,
    "cut/tile": 1024,
    "cut/sigma": 1.4,
    "cut/head_ratio": 0.34,
    "cut/matting": True,
    "cut/format": "PNG (RGBA)",
    # Композит: --blur 0.5, остальные значения — аргументы CLI по умолчанию.
    "compose/blur": 0.5,
    "compose/shadow": 0.22,
    "compose/tone": 1.06,
    "compose/grain": 4.5,
    "compose/seed": 7,
    # Фон: рабочий провайдер и черновики без автоматического апскейла.
    "bg/provider_api": "cloudflare",
    "bg/seed": 7,
    "bg/upscale": False,
    "bg/prompt": "realistic photo, no people, no text, soft overcast light",
    "models/upscale": "realesr-general-x4v3",
}


def apply_default_presets(settings: QSettings) -> bool:
    """Записать предустановки один раз. True — значения были изменены."""
    try:
        version = int(settings.value("app/defaults_version", 0))
    except (TypeError, ValueError):
        version = 0
    if version >= DEFAULTS_VERSION:
        return False
    for key, value in APP_DEFAULTS.items():
        settings.setValue(key, value)
    settings.setValue("app/defaults_version", DEFAULTS_VERSION)
    settings.sync()
    return True
