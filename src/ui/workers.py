"""Фоновый воркер для операций ``src.core``.

Операция выполняется в ``QThread``, прогресс и результат приходят в GUI
через сигналы. Отмена кооперативная: воркер выставляет флаг, а ядро
проверяет его в точках ``check_cancel`` между тайлами и этапами.
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.progress import CancelledError


class CoreWorker(QThread):
    """Запускает одну функцию ядра и сообщает о ходе выполнения."""

    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = dict(kwargs)
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Запросить отмену — будет проверена на следующей точке ядра."""
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def report(self, percent: int, message: str = "") -> None:
        """Колбэк прогресса; emissions из рабочего потока безопасны в Qt."""
        if self.is_cancelled():
            raise CancelledError("Операция отменена")
        self.progress.emit(int(percent), str(message))

    def run(self) -> None:
        kwargs = dict(self._kwargs)
        kwargs.setdefault("progress", self.report)
        kwargs.setdefault("cancelled", self.is_cancelled)
        try:
            result = self._func(*self._args, **kwargs)
            if self.is_cancelled():
                raise CancelledError("Операция отменена")
        except CancelledError:
            self.cancelled.emit()
        except Exception as exc:  # любая ошибка ядра должна дойти до лога GUI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.succeeded.emit(result)
