"""Прогресс и кооперативная отмена длинных операций.

Функции ядра получают необязательные ``progress(percent, message)`` и
``cancelled() -> bool``. CLI их не передаёт, поэтому поведение command line
не меняется; GUI передаёт колбэки воркера.
"""
from __future__ import annotations

import time
from collections.abc import Callable

ProgressFn = Callable[[int, str], None] | None
CancelFn = Callable[[], bool] | None


class CancelledError(RuntimeError):
    """Операция прервана пользователем."""


def maybe_report(progress: ProgressFn, percent: int, message: str = "") -> None:
    """Сообщить прогрузчику о прогрессе, если колбэк задан."""
    if progress is not None:
        progress(int(percent), str(message))


def check_cancel(cancelled: CancelFn) -> None:
    """Прервать операцию, если пользователь нажал «Стоп»."""
    if cancelled is not None and cancelled():
        raise CancelledError("Операция отменена")


def scaled(progress: ProgressFn, lo: int, hi: int) -> ProgressFn:
    """Сжать диапазон 0..100 вложенного этапа в ``lo..hi``."""
    if progress is None:
        return None

    def _scaled(percent: int, message: str = "") -> None:
        if percent < 0:
            progress(-1, str(message))
        else:
            progress(lo + (hi - lo) * int(percent) // 100, str(message))

    return _scaled


def sleep_or_cancel(seconds: float, cancelled: CancelFn) -> None:
    """Пауза между повторами, которую можно прервать кнопкой «Стоп»."""
    deadline = time.monotonic() + seconds
    while True:
        check_cancel(cancelled)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))
