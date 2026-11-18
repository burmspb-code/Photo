"""Проверенные предустановки приложения (утверждённый результат C, 2026-11-17).

Значения выбраны по карточке результата и командам, которые дали нужные
вырезку и композит. ``apply_default_presets`` вызывается при запуске GUI:
он однократно исправляет устаревшие ключи (например, ``cut/model = u2netp``),
но не перетирает пользовательские изменения после своей первой записи.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings

# Поднимать при изменении набора предустановок — заставит применить их заново.
DEFAULTS_VERSION = 2

# Промпт — одноразовый ввод, а не настройка: в поле видна подсказка, которая
# исчезает при первом же нажатии. Текст обязательных частей (realistic photo,
# no people, no text) ядро добавит само — в подсказке они не нужны.
PROMPT_PLACEHOLDER = (
    "Например: реалистичное фото 1024×1024, в центре — созвездие Большой "
    "Медведицы, проглядывающее сквозь разрывы туч на облачном ночном небе."
)

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
    # Фон: рабочий провайдер и конечный размер файла (1K/2K/4K, 4:3).
    "bg/provider_api": "cloudflare",
    "bg/seed": 7,
    "bg/size": "2K",
    # Апскейл: ×2 — EDSR (быстрый, сохраняет мелкие детали), ×4 — Real-ESRGAN.
    "upscale/factor": 2,
    # Подсказки о следующем шаге в нижнем инфоокне можно отключить.
    "ui/hints": True,
}


def apply_default_presets(settings: QSettings) -> bool:
    """Записать предустановки один раз. True — значения были изменены.

    Старый ``bg/prompt`` удаляется при каждом запуске: раньше он хранил текст
    прошлой генерации и сразу появлялся в поле ввода вместо подсказки.
    ``models/upscale`` удаляется при миграции — модель теперь выбрана кратностью.
    """
    settings.remove("bg/prompt")
    settings.remove("models/upscale")
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
