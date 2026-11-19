"""Единый набор настраиваемых параметров вырезки.

Используется ядром (``cutout``), GUI (``ui/defaults``, вкладка «Вырезка»)
и CLI (``photo_pipeline``). Значения по умолчанию повторяют рецепт результата C;
изменение числа здесь автоматически меняет и предустановку в настройках.

Ключи словаря совпадают с именами параметров ядра и с ключами QSettings
без префикса ``cut/`` (например, ``tile`` → ``cut/tile``).
"""
from __future__ import annotations

CUT_DEFAULTS: dict[str, object] = {
    # Сегментация: модель задаётся отдельно, здесь — геометрия тайлов.
    "portrait": True,
    "tile": 1024,
    "overlap": 0.5,
    # Кромка: levels — жёсткие границы альфы, detail — локальный контраст,
    # head — дополнительное сглаживание верхней части силуэта.
    "sigma": 1.4,
    "head_ratio": 0.34,
    "levels_lo": 0.10,
    "levels_hi": 0.90,
    "detail_gain": 7.0,
    "detail_blur": 2.5,
    "detail_weight": 0.6,
    "head_blur": 6.0,
    "head_weight": 0.6,
    "matting": True,
    # Страховка цельным кадром.
    "global_shape": True,
    "global_min_fraction": 0.001,
    "global_feather": 3.0,
    # Чистка шума перекрытий тайлов и неполной альфы внутри силуэта.
    "stabilize": True,
    "stabilize_min_mid": 0.03,
    "stabilize_noisy_mid": 0.10,
    "stabilize_min_comps": 50,
    "stabilize_keep_ratio": 0.02,
    "stabilize_dilate": 7,
    "stabilize_inner": 3,
    # Удаление мелких обособленных элементов.
    "isolated": True,
    "isolated_ratio": 0.15,
    "isolated_gap": 24,
    "isolated_halo": 32,
    # Заливка замкнутых остатков фона в верхней части силуэта (сквозь волосы).
    "fill_holes": True,
    "hole_min_area": 250,
    "hole_max_area": 60000,
    "hole_top_fraction": 0.5,
    # Уплотнение полупрозрачной каймы волос в верхней части силуэта.
    "hair_refine": True,
    "hair_top_fraction": 0.30,
    "hair_min_mid": 25000,
    "hair_gain": 3.0,
    # Удаление светло-голубого фона между прядями по цветовому расстоянию.
    "color_gaps": True,
    "color_gap_lo": 45.0,
    "color_gap_hi": 100.0,
    "color_gap_top_fraction": 0.35,
    "color_gap_min_blue": 25.0,
}
