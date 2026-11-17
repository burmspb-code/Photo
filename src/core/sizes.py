"""Пресеты размера сгенерированного фона.

Соотношение сторон 4:3 — как у исходного снимка DSC00103 (1632×1224).
Пресет задаёт конечный размер файла: если провайдер отдаёт меньше, результат
проходит ESRGAN ×4 и при необходимости уменьшается до точного значения.
"""
from __future__ import annotations

SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "1K": (1024, 768),
    "2K": (2048, 1536),
    "4K": (4096, 3072),
}
SIZE_ORDER = tuple(SIZE_PRESETS)


def size_for(preset: str | None) -> tuple[int, int] | None:
    """Размер по имени пресета; None, если пресет не задан."""
    return SIZE_PRESETS.get(str(preset or "").upper()) if preset else None
