"""Плавное открытие списков без смещения выделенной строки."""
from __future__ import annotations

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QComboBox

from src.ui.animated_combo import AnimatedComboBox, _DURATION_MS
from tests.gui_case import GuiTestCase


class TestAnimatedComboBox(GuiTestCase):
    def setUp(self) -> None:
        self.combo = AnimatedComboBox()
        self.combo.addItems(["один", "два", "три"])

    def tearDown(self) -> None:
        self.combo.hidePopup()
        self.combo.deleteLater()
        self.process_events()

    def test_is_qcombobox(self) -> None:
        # Замена должна быть прозрачной для кода, работающего с QComboBox.
        self.assertIsInstance(self.combo, QComboBox)

    def test_show_starts_opacity_animation(self) -> None:
        self.combo.showPopup()
        self.process_events()

        anim = self.combo._popup_animation
        self.assertIsNotNone(anim)
        self.assertEqual(anim.property("duration"), _DURATION_MS)

    def test_popup_position_is_not_animated(self) -> None:
        """Выделенная строка не должна «уезжать» вниз при открытии."""
        self.combo.showPopup()
        self.process_events()
        container = self.combo.view().parent()
        final_pos = container.pos()
        self.process_events()
        self.assertEqual(container.pos(), final_pos)
        # Анимируется только прозрачность.
        self.assertLess(container.windowOpacity(), 1.0)

    def test_hide_restores_opacity(self) -> None:
        self.combo.showPopup()
        self.process_events()
        container = self.combo.view().parent()
        self.assertLess(container.windowOpacity(), 1.0)

        self.combo.hidePopup()
        self.process_events()
        self.assertEqual(container.windowOpacity(), 1.0)
        self.assertIsNone(self.combo._popup_animation)

    def test_animation_finishes_at_full_opacity(self) -> None:
        self.combo.showPopup()
        self.process_events()
        container = self.combo.view().parent()

        # Даём анимации завершиться в реальном event loop.
        loop = QEventLoop()
        QTimer.singleShot(_DURATION_MS + 120, loop.quit)
        loop.exec()

        # Qt хранит opacity с точностью до 1/255, 254/255 — тоже готово.
        self.assertAlmostEqual(container.windowOpacity(), 1.0, delta=0.01)
        self.assertIsNone(self.combo._popup_animation)

    def test_rapid_reopen_leaves_one_animation(self) -> None:
        self.combo.showPopup()
        self.process_events()
        self.combo.hidePopup()
        self.combo.showPopup()
        self.process_events()
        self.assertIsNotNone(self.combo._popup_animation)
