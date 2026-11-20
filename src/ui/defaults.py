"""Проверенные предустановки приложения (утверждённый результат C, 2026-11-17).

Значения выбраны по карточке результата и командам, которые дали нужные
вырезку и композит. ``apply_default_presets`` вызывается при запуске GUI:
он однократно записывает проверенные значения, но не перетирает пользовательские
изменения после своей первой записи. Модель вне текущего списка ``CUT_MODELS``
исправляется при каждом запуске — отдельно от версии предустановок.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings

from src.core.cut_params import CUT_DEFAULTS

# Список моделей вырезки — единственный источник для GUI и диалога настроек.
# CLI принимает любую модель rembg, но в интерфейсе оставляем только проверенные:
# две основные BiRefNet, альтернативная ISNet и лёгкая u2netp для быстрых превью.
CUT_MODELS: tuple[str, ...] = (
    "birefnet-general",
    "birefnet-portrait",
    "isnet-general-use",
    "u2netp",
)
CUT_MODEL_PREVIEW = "u2netp"

# Короткие подсказки на элементах комбо — чтобы назначение моделей было видно
# прямо в выпадающем списке, без похода в документацию.
CUT_MODEL_HINTS: dict[str, str] = {
    "birefnet-general": "Основная модель: лучший баланс качества и скорости, мягкая кромка.",
    "birefnet-portrait": "Для портретов: точнее края лица и волос.",
    "isnet-general-use": "Другая архитектура: пробовать, если BiRefNet ошибся на кадре.",
    "u2netp": "Лёгкая модель для быстрого предпросмотра: края грубее, зато в разы быстрее.",
}

# Поднимать при изменении набора предустановок — заставит применить их заново.
DEFAULTS_VERSION = 6

# Промпт — одноразовый ввод, а не настройка: в поле видна подсказка, которая
# исчезает при первом же нажатии. Текст обязательных частей (realistic photo,
# no people, no text) ядро добавит само — в подсказке они не нужны.
PROMPT_PLACEHOLDER = "Создай реалистичное фото северного сияния на ночном небе"

APP_DEFAULTS: dict[str, object] = {
    # Вырезка: все параметры алгоритма берутся из одного набора, что и ядро/CLI.
    **{f"cut/{key}": value for key, value in CUT_DEFAULTS.items()},
    "cut/model": "birefnet-general",
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

    # Модель, которой больше нет в списке, исправляем при любом запуске и не
    # поднимаем из-за этого DEFAULTS_VERSION: иначе перезаписались бы все
    # пользовательские пороги вырезки. Значение u2netp теперь тоже допустимо
    # (быстрая модель для превью) и сохраняется как есть.
    changed = False
    stored_model = settings.value("cut/model")
    if stored_model is not None and stored_model not in CUT_MODELS:
        settings.setValue("cut/model", APP_DEFAULTS["cut/model"])
        changed = True

    try:
        version = int(settings.value("app/defaults_version", 0))
    except (TypeError, ValueError):
        version = 0
    if version >= DEFAULTS_VERSION:
        if changed:
            settings.sync()
        return changed
    for key, value in APP_DEFAULTS.items():
        settings.setValue(key, value)
    settings.setValue("app/defaults_version", DEFAULTS_VERSION)
    settings.sync()
    return True
