"""Задачи для GUI: пути и параметры на вход, путь к результату на выход.

Тяжёлые модули импортируются внутри функций — ``import src.core.tasks`` не
загружает rembg и ONNX-модели. Все задачи принимают колбэки ``progress`` и
``cancelled``; CLI их не использует.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from src.core.progress import check_cancel, maybe_report, scaled
from src.core.settings import PROJECT_ROOT

DATA_DIR = PROJECT_ROOT / "data"
BG_DIR = DATA_DIR / "bg"
WORK_DIR = DATA_DIR / "work"
CUTOUT_FILE = WORK_DIR / "cutout.png"
RESULT_FILE = WORK_DIR / "result.jpg"
PROMPT_BASE = "realistic photo, no people, no text"


def _path(value, default) -> str:
    path = Path(value) if value else Path(default)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _prompt(value) -> str:
    text = str(value or "").strip()
    if PROMPT_BASE.lower() not in text.lower():
        text = f"{text}, {PROMPT_BASE}" if text else PROMPT_BASE
    return text


def cut_task(source, out=None, *, options=None, progress=None, cancelled=None) -> str:
    """Вырезать объект и сохранить RGBA PNG."""
    from .cutout import make_cutout
    from .image import _write

    params = options or {}
    dest = _path(out, CUTOUT_FILE)
    maybe_report(progress, 0, "Вырезка: старт")
    cut = make_cutout(
        source,
        portrait=bool(params.get("portrait", True)),
        model=params.get("model"),
        tile=int(params.get("tile", 1024)),
        sigma=float(params.get("sigma", 1.4)),
        head_ratio=float(params.get("head_ratio", 0.34)),
        matting=bool(params.get("matting", True)),
        progress=scaled(progress, 5, 90),
        cancelled=cancelled,
    )
    check_cancel(cancelled)
    maybe_report(progress, 95, "Сохранение вырезки")
    _write(dest, cut)
    maybe_report(progress, 100, "Вырезка сохранена")
    return dest


def genbg_task(prompt, out=None, *, options=None, progress=None, cancelled=None) -> str:
    """Сгенерировать фон в ``data\\bg\\`` и при необходимости апскейлить."""
    from .backgrounds import genbg

    params = options or {}
    default_out = BG_DIR / f"generated-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    dest = _path(out, default_out)
    maybe_report(progress, 0, "Генерация фона: старт")
    genbg(
        _prompt(prompt),
        dest,
        seed=int(params.get("seed", 7)),
        do_upscale=bool(params.get("do_upscale", False)),
        provider=str(params.get("provider", "cloudflare")),
        model=params.get("model"),
        progress=scaled(progress, 5, 100),
        cancelled=cancelled,
    )
    check_cancel(cancelled)
    maybe_report(progress, 100, "Фон сохранён")
    return dest


def upscale_task(src, out=None, *, options=None, progress=None, cancelled=None) -> str:
    """Апскейл изображения ×4; по умолчанию рядом с исходником."""
    from .upscale import upscale

    source = Path(src)
    if out:
        dest = _path(out, out)
    else:
        stem = re.sub(r"-4x$", "", source.stem)
        dest = _path(None, source.with_name(f"{stem}-4x{source.suffix or '.jpg'}"))
    maybe_report(progress, 0, "Апскейл: старт")
    upscale(source, dest, progress=scaled(progress, 5, 100), cancelled=cancelled)
    check_cancel(cancelled)
    return dest


def compose_task(cut, background, out=None, *, options=None,
                 progress=None, cancelled=None) -> str:
    """Собрать композит из вырезки и фона, сохранить JPEG."""
    from .compose import composite
    from .image import _read, _write

    params = options or {}
    dest = _path(out, RESULT_FILE)
    maybe_report(progress, 0, "Сборка композита: старт")
    cut_img = _read(cut)
    if cut_img is None or cut_img.ndim != 3 or cut_img.shape[2] < 4:
        raise ValueError("нужен PNG с альфа-каналом — сначала выполните вырезку")
    result = composite(
        cut_img,
        background,
        tone=float(params.get("tone", 1.06)),
        shadow=float(params.get("shadow", 0.22)),
        grain=float(params.get("grain", 4.5)),
        blur_bg=float(params.get("blur", 0.5)),
        seed=int(params.get("seed", 7)),
        progress=scaled(progress, 5, 95),
        cancelled=cancelled,
    )
    check_cancel(cancelled)
    maybe_report(progress, 95, "Сохранение композита")
    _write(dest, result)
    maybe_report(progress, 100, "Композит сохранён")
    return dest
