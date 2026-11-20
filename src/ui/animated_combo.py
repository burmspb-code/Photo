"""Комбобокс с плавным открытием списка без смещения popup.

Стандартный ``QComboBox`` показывает popup мгновенно, что выглядит как
резкое «дёрганье». Здесь список проявляется через анимацию прозрачности —
без сдвига позиции: вместе с popup не ездит выделенная строка, и она не
возвращается обратно при завершении анимации. Стрелка рисуется из PNG
в QSS (современный шеврон), поэтому анимация не мешает её отрисовке.
"""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PyQt6.QtWidgets import QComboBox

# 170 мс — достаточно заметно, но не тормозит выбор пункта.
_DURATION_MS = 170


class AnimatedComboBox(QComboBox):
    """QComboBox с плавным появлением popup (только fade, без slide)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_animation: QPropertyAnimation | None = None
        self._popup_open = False

    def _popup_container(self):
        """Внутренний QFrame popup — настоящий владелец окна со списком."""
        view = self.view()
        return view.parent() if view is not None else None

    def _reset_popup(self) -> None:
        """Вернуть прозрачность popup в норму после прерванной анимации."""
        anim = self._popup_animation
        if anim is not None:
            anim.stop()
            self._popup_animation = None
        container = self._popup_container()
        if container is not None:
            container.setWindowOpacity(1.0)

    def _start_animation(self) -> None:
        if not self._popup_open:
            return  # список уже закрыли, пока ждали следующий тик event loop
        container = self._popup_container()
        if container is None:
            return

        # Позициюpopup НЕ трогаем: Qt уже разместил его под полем ввода,
        # а сдвиг заставляет выделенную строку «уезжать» при открытии.
        container.setWindowOpacity(0.0)
        anim = QPropertyAnimation(container, b"windowOpacity", self)
        anim.setDuration(_DURATION_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(self._on_animation_finished)
        anim.start()
        self._popup_animation = anim

    def _on_animation_finished(self) -> None:
        self._popup_animation = None
        container = self._popup_container()
        if container is not None:
            container.setWindowOpacity(1.0)

    def showPopup(self) -> None:
        self._popup_open = True
        self._reset_popup()
        super().showPopup()
        # Контейнер popup создаётся/позиционируется внутри showPopup(),
        # поэтому начинаем анимацию следующим тиком — после размещения.
        QTimer.singleShot(0, self._start_animation)

    def hidePopup(self) -> None:
        self._popup_open = False
        self._reset_popup()
        super().hidePopup()
