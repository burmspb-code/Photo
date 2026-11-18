"""Главное окно приложения замены фона.

Три зоны:
    1. меню + тулбар;
    2. результат: параметры задачи слева, предпросмотр с вкладками справа;
    3. служебные сообщения: прогресс, кнопка «Стоп», лог.

Вырезка, генерация фона, апскейл и сборка композита выполняются в
``CoreWorker`` (QThread) с прогрессом и отменой; логика — в ``src.core``.
"""
from __future__ import annotations

import ctypes
import html
import logging
import math
import sys
from ctypes import wintypes
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QLineF,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSettings,
    QSignalBlocker,
    QSize,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFontMetrics,
    QIcon,
    QImage,
    QImageReader,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QRegion,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGroupBox,
    QMenuBar,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStyle,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.cutout import cut_advisory
from src.core.image import _read, _write
from src.core.settings import normalize_factor
from src.core.tasks import CUTOUT_FILE, compose_task, cut_task, genbg_task, upscale_task

from .about_dialog import AboutDialog
from .defaults import APP_DEFAULTS, PROMPT_PLACEHOLDER
from .settings_dialog import SettingsDialog
from .styles import THEMES
from .workers import CoreWorker

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
BG_DIR = DATA_DIR / "bg"

LOG = logging.getLogger(__name__)

PREVIEW_TABS = ("Исходник", "Вырезка", "Фон", "Результат", "До — После")
# Сохранять можно только промежуточные результаты; исходное фото не сохраняем.
SAVE_TABS = ("Вырезка", "Фон", "Результат", "До — После")
SAVE_PRESETS = {
    "Вырезка": ("cutout.png", "PNG images (*.png);;JPEG images (*.jpg *.jpeg)"),
    "Фон": ("background.jpg", "JPEG images (*.jpg *.jpeg);;PNG images (*.png)"),
    "Результат": ("result.jpg", "JPEG images (*.jpg *.jpeg);;PNG images (*.png)"),
    "До — После": ("before-after.jpg", "JPEG images (*.jpg *.jpeg);;PNG images (*.png)"),
}
# Кратность к вписанному кадру: 2^(value/100), поэтому -100 → ÷2, +200 → ×4.
ZOOM_MIN, ZOOM_MAX = -100, 200
ZOOM_LABELS = ((200, "×4"), (100, "×2"), (0, "×1"), (-100, "÷2"))
CUT_MODELS = (
    "birefnet-general",
    "birefnet-portrait",
    "birefnet-general-lite",
    "birefnet-general-fp16",
    "birefnet-massive",
    "isnet-general-use",
    "u2net",
    "u2netp",
)
IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.webp)"
# Панель задач фиксированной ширины: QSplitter.setSizes() задаёт только стартовые
# пропорции, поэтому при пересчёте лэйаута (загрузка фото, генерация, resize)
# левая панель «убегала». Жёсткий pre/min/max в setFixedWidth этого не допускает.
PARAMS_WIDTH = 340

# Нативная обработка краёв безрамочного окна в Windows.
WM_NCHITTEST = 0x0084
_HT_EDGES = {
    (-1, -1): 13,  # HTTOPLEFT
    (-1, 0): 10,   # HTLEFT
    (-1, 1): 16,   # HTBOTTOMLEFT
    (0, -1): 12,   # HTTOP
    (0, 1): 15,    # HTBOTTOM
    (1, -1): 14,   # HTTOPRIGHT
    (1, 0): 11,    # HTRIGHT
    (1, 1): 17,    # HTBOTTOMRIGHT
}


class _WinMessage(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


LEVEL_COLORS = {
    "OK": "#4ade80",
    "HINT": "#c4b5fd",
    "INFO": "#93c5fd",
    "WARN": "#fbbf24",
    "ERROR": "#f87171",
}


def _icon(name: str) -> QIcon:
    enum = getattr(QStyle.StandardPixmap, name, None)
    return QApplication.style().standardIcon(enum) if enum is not None else QIcon()


def _solid_icon(name: str, color: str) -> QIcon:
    """Значок с фиксированной заливкой: не зависит от темы и виден на любом фоне."""
    pixmap = _icon(name).pixmap(QSize(32, 32))
    if pixmap.isNull():
        return QIcon()
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return QIcon(pixmap)


MAX_PREVIEW_SIDE = 4096  # QPixmap большего размера падает даже при успешном QImage


def _preview_downscale(path: str | Path) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Размеры (было → стало), если превью было уменьшено; иначе None.

    ``QImageReader.size()`` читает только заголовок, поэтому работает и для
    кадров, которые ``QImage`` не декодирует из-за лимита аллокации.
    """
    size = QImageReader(str(path)).size()
    if not size.isValid():
        return None
    original = (size.width(), size.height())
    if max(original) <= MAX_PREVIEW_SIDE:
        return None
    factor = MAX_PREVIEW_SIDE / max(original)
    preview = (max(1, round(original[0] * factor)), max(1, round(original[1] * factor)))
    return original, preview


def _image_size(path: str | Path) -> tuple[int, int] | None:
    """Настоящий размер файла из заголовка, без декодирования картинки."""
    size = QImageReader(str(path)).size()
    return (size.width(), size.height()) if size.isValid() else None


def _image_info(path: str | Path) -> tuple[str, str]:
    """Подпись «имя · WxH» и tooltip с путём и весом файла.

    Разрешение читается из заголовка файла, а не из уменьшенного превью: окно
    показывает копию до ``MAX_PREVIEW_SIDE``, но подпись должна сообщать
    настоящий размер файла на диске.
    """
    file = Path(path)
    dimensions = _image_size(file)
    resolution = (
        f"{dimensions[0]}×{dimensions[1]}" if dimensions else "размер неизвестен"
    )
    label = f"{file.name} · {resolution}"
    try:
        mb = file.stat().st_size / (1024 * 1024)
        weight = f"{mb:.1f} МБ".replace(".", ",")
    except OSError:
        weight = "недоступен"
    return label, f"{file}\n{resolution} · {weight}"


def _scaled_qimage(image: QImage) -> QImage:
    """Уменьшить кадр для превью, сохраняя пропорции."""
    side = max(image.width(), image.height())
    if side <= MAX_PREVIEW_SIDE:
        return image
    factor = MAX_PREVIEW_SIDE / side
    return image.scaled(
        max(1, round(image.width() * factor)),
        max(1, round(image.height() * factor)),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _load_qimage(path: str) -> QImage:
    """Прочитать картинку для превью, обойдя лимит аллокации Qt.

    ``QImage(path)`` молча возвращает пустой объект, если декодированное
    изображение больше лимита ``QImageReader`` (по умолчанию 256 МБ). Такое
    бывает после апскейла ×4: 3840×2160 → 15360×8640. ``cv2.imdecode`` этого
    лимита не имеет, поэтому тяжёлые кадры читаем через него. В любом случае
    превью уменьшается до ``MAX_PREVIEW_SIDE``: ``QPixmap`` на 15360×8640
    приводит к падению процесса. Полный размер сохраняется из исходного файла.
    """
    image = QImage(path)
    if not image.isNull():
        return _scaled_qimage(image)
    try:
        bgr = _read(path)
    except Exception:  # битый или недоступный файл — вернём пустой QImage
        return QImage()
    if bgr is None or bgr.ndim != 3 or bgr.shape[2] not in (3, 4):
        return QImage()
    height, width = bgr.shape[:2]
    scale = min(1.0, MAX_PREVIEW_SIDE / max(height, width))
    if scale < 1.0:
        bgr = cv2.resize(
            bgr, (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
        height, width = bgr.shape[:2]
    if bgr.shape[2] == 4:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGRA2RGBA)
        fmt, bytes_per_line = QImage.Format.Format_RGBA8888, width * 4
    else:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        fmt, bytes_per_line = QImage.Format.Format_RGB888, width * 3
    return QImage(rgb.data, width, height, bytes_per_line, fmt).copy()


def _combine_full_res(before_path: str | Path, after_path: str | Path) -> np.ndarray | None:
    """Соединить «До — После» в полном размере; None, если файл не читается."""
    before, after = _read(before_path), _read(after_path)
    if before is None or after is None:
        return None

    def to_bgr(img: np.ndarray) -> np.ndarray:
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.shape[2] == 4:  # наложить альфу на белый, как делает QPainter
            alpha = img[:, :, 3:4].astype(np.float32) / 255.0
            rgb = img[:, :, :3].astype(np.float32) * alpha + 255.0 * (1.0 - alpha)
            return rgb.astype(np.uint8)
        return img[:, :, :3]

    before, after = to_bgr(before), to_bgr(after)
    height = max(before.shape[0], after.shape[0])

    def fit(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        width = max(1, round(w * height / h))
        return cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)

    left, right = fit(before), fit(after)
    gap = 6
    combined = np.full((height, left.shape[1] + gap + right.shape[1], 3), 255, dtype=np.uint8)
    combined[:, :left.shape[1]] = left
    combined[:, left.shape[1] + gap:] = right
    return combined


class ImagePreview(QLabel):
    """Превью с масштабированием и панорамированием перетаскиванием."""

    moved = pyqtSignal()

    def __init__(self, placeholder: str = "Изображение не загружено"):
        super().__init__(placeholder)
        self._source: QPixmap | None = None
        self._source_path: str | None = None
        self._scaled: QPixmap | None = None
        self._zoom = 0.0  # 0 = вписать в виджет
        self._offset = QPoint(0, 0)
        self._drag_origin: QPoint | None = None
        self.placeholder = placeholder
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("preview")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(240, 180)
        self.setMouseTracking(True)

    def set_image(self, path: str | Path) -> bool:
        image = _load_qimage(str(path))
        if image.isNull():
            self.clear_image("Не удалось прочитать изображение")
            return False
        self._source = QPixmap.fromImage(image)
        self._source_path = str(path)  # полный размер берём из файла при сохранении
        self._reset_view()
        self._rescale()
        self.moved.emit()
        return True

    def clear_image(self, text: str | None = None) -> None:
        self._source = None
        self._source_path = None
        self._scaled = None
        self._drag_origin = None
        self.unsetCursor()
        self.setText(text or self.placeholder)
        self.update()
        self.moved.emit()

    def source_pixmap(self) -> QPixmap | None:
        """Превью (может быть уменьшено) — для отображения и фолбэка сохранения."""
        return self._source

    def source_path(self) -> str | None:
        """Путь к исходному файлу в полном размере."""
        return self._source_path

    @property
    def zoom(self) -> float:
        return self._zoom

    def fit_factor(self) -> float:
        """Во сколько раз вписанное изображение меньше original."""
        if self._source is None:
            return 1.0
        return min(
            self.width() / self._source.width(),
            self.height() / self._source.height(),
        )

    def set_zoom(self, zoom: float) -> None:
        if zoom == 0.0:
            self._offset = QPoint(0, 0)
        self._zoom = zoom
        self._rescale()
        self.moved.emit()

    def reset_view(self) -> None:
        self._reset_view()
        self._rescale()
        self.moved.emit()

    def _reset_view(self) -> None:
        self._zoom = 0.0
        self._offset = QPoint(0, 0)

    def image_rect(self) -> QRect:
        """Фактический прямоугольник картинки в координатах виджета."""
        pixmap = self._scaled
        if pixmap is None:
            return QRect()
        x = (self.width() - pixmap.width()) // 2 + self._offset.x()
        y = (self.height() - pixmap.height()) // 2 + self._offset.y()
        return QRect(x, y, pixmap.width(), pixmap.height())

    def _rescale(self) -> None:
        if self._source is None:
            return
        if self._zoom == 0.0:
            size = self.size()
        else:
            size = QSize(
                round(self._source.width() * self._zoom),
                round(self._source.height() * self._zoom),
            )
        self._scaled = self._source.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._clamp_offset()
        self.update()

    def _clamp_offset(self) -> None:
        rect = self.image_rect()
        if rect.width() <= self.width():
            new_x = (self.width() - rect.width()) // 2
        else:
            new_x = min(0, max(self.width() - rect.width(), rect.x()))
        if rect.height() <= self.height():
            new_y = (self.height() - rect.height()) // 2
        else:
            new_y = min(0, max(self.height() - rect.height(), rect.y()))
        dx, dy = new_x - rect.x(), new_y - rect.y()
        if dx or dy:
            self._offset += QPoint(dx, dy)

    def paintEvent(self, event) -> None:
        if self._scaled is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        rect = self.image_rect()
        painter.drawPixmap(rect.topLeft(), self._scaled)

    def enterEvent(self, event) -> None:
        if self._scaled is not None:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._drag_origin is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._scaled is not None:
            self._drag_origin = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is not None:
            position = event.position().toPoint()
            self._offset += position - self._drag_origin
            self._drag_origin = position
            self._clamp_offset()
            self.update()
            self.moved.emit()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._scaled is not None
                else Qt.CursorShape.ArrowCursor
            )
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()
        self.moved.emit()


class ElidedLabel(QLabel):
    """Подпись, сокращающая середину: имя и расширение остаются видимыми."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self._elide()

    def setText(self, text: str) -> None:
        self._full_text = text
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        text = QFontMetrics(self.font()).elidedText(
            self._full_text, Qt.TextElideMode.ElideMiddle, max(1, self.width())
        )
        super().setText(text)


class HoverOverlay(QFrame):
    """Панель поверх изображения: проявляется при действии и гаснет через 5 с."""

    HIDE_DELAY_MS = 5000
    FADE_MS = 350

    def __init__(self, object_name: str):
        super().__init__()
        self.setObjectName(object_name)
        self.can_reveal: callable | None = None
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(self.FADE_MS)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.HIDE_DELAY_MS)
        self._timer.timeout.connect(self._hide)

    def reveal(self) -> None:
        """Показать панель и отложить затухание на 5 секунд."""
        if self.can_reveal is not None and not self.can_reveal():
            return
        self._timer.stop()
        self._fade.stop()
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start()

    def _hide(self) -> None:
        self._fade.stop()
        self._fade.setEndValue(0.0)
        self._fade.start()

    def enterEvent(self, event) -> None:
        self.reveal()
        super().enterEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self.reveal()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        # Не гасим сразу: панель должна жить 5 с после последнего действия.
        super().leaveEvent(event)


class ZoomOverlay(HoverOverlay):
    """Вертикальная шкала кратности увеличения: ×4 … ×1 … ÷2."""

    def __init__(self):
        super().__init__("zoomBar")
        self.setToolTip("Ползунок или колесо мыши — кратность увеличения")


class CloseButton(QPushButton):
    """Квадратная кнопка с геометрически точным крестиком по центру.

    Шрифтовый глиф «×» сидит в кегле со смещением, поэтому крест рисуется
    линиями относительно центра виджета — он остаётся симметричным в любой
    теме и при любом масштабе текста.
    """

    def paintEvent(self, event) -> None:
        super().paintEvent(event)  # фон, рамка и состояние hover из QSS
        rect = self.rect()
        # QRect::center() у чётного размера округляет вверх-влево (10,10 вместо
        # 10.5,10.5) — из-за этого крест кажется смещённым внутри квадрата.
        cx = (rect.left() + rect.right()) / 2
        cy = (rect.top() + rect.bottom()) / 2
        half = min(rect.width(), rect.height()) / 2 - 5
        pen = QPen(self.palette().color(QPalette.ColorRole.ButtonText))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)
        painter.drawLine(QLineF(cx - half, cy - half, cx + half, cy + half))
        painter.drawLine(QLineF(cx + half, cy - half, cx - half, cy + half))
        painter.end()


class AdvisoryToast(HoverOverlay):
    """Всплывающее предупреждение: живёт 5 с, закрывается крестиком."""

    def __init__(self):
        super().__init__("advisoryToast")
        self.setMaximumWidth(420)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 6, 8)
        layout.setSpacing(8)
        self.label = QLabel()
        self.label.setObjectName("advisoryText")
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)
        self.close_button = CloseButton()
        self.close_button.setObjectName("advisoryClose")
        self.close_button.setAccessibleName("Закрыть")
        self.close_button.setFixedSize(22, 22)
        self.close_button.clicked.connect(self.dismiss)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        self._fade.finished.connect(self._on_fade_finished)
        self.hide()

    def show_notes(self, notes: list[str]) -> None:
        self.label.setText("⚠ " + "\n".join(notes))
        # Сначала показываем: скрытый виджет не разкладывает лэйаут, и крестик
        # остаётся с нулевой геометрией.
        self.show()
        self.adjustSize()
        self.reveal()

    def reveal(self) -> None:
        self.show()
        self.raise_()
        super().reveal()

    def _on_fade_finished(self) -> None:
        if self._effect.opacity() == 0.0:
            self.hide()

    def dismiss(self) -> None:
        """Закрыть сразу — по крестику, смене фото или уходу с вкладки."""
        self._timer.stop()
        self._fade.stop()
        self._effect.setOpacity(0.0)
        self.hide()


class PreviewArea(QFrame):
    """Область вкладок с наложенными прозрачными панелями управления."""

    wheel_stepped = pyqtSignal(int)

    def __init__(self, tabs: QTabWidget, zoom_overlay: ZoomOverlay,
                 advisory_toast: AdvisoryToast | None = None):
        super().__init__()
        self.setObjectName("previewArea")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)

        self.tabs = tabs
        self.zoom_overlay = zoom_overlay
        self.advisory_toast = advisory_toast
        self.can_interact: callable | None = None  # callable -> bool, есть ли загруженное фото
        self.image_rect_provider = None  # callable -> list[QRect] в координатах area
        overlays = [zoom_overlay]
        if advisory_toast is not None:
            overlays.append(advisory_toast)
        for overlay in overlays:
            overlay.setParent(self)
            # Панели не лежат в слое, поэтому размер берём из их sizeHint.
            overlay.adjustSize()
            overlay.raise_()
        self._place_zoom()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _inside(self, obj) -> bool:
        return isinstance(obj, QWidget) and (obj is self or self.isAncestorOf(obj))

    def _page_rect(self) -> QRect:
        """Прямоугольник страницы вкладки, где рисуется фото."""
        page = self.tabs.currentWidget()
        if page is None:
            return self.rect()
        return QRect(page.mapTo(self, QPoint(0, 0)), page.size())

    def _place_zoom(self) -> None:
        """Шкала закреплена в правом верхнем углу страницы с фото."""
        page = self._page_rect()
        x = page.right() - self.zoom_overlay.width() - 10
        y = page.top() + 10
        x = max(page.left(), min(x, page.right() - self.zoom_overlay.width()))
        y = max(page.top(), min(y, page.bottom() - self.zoom_overlay.height()))
        self.zoom_overlay.move(x, y)
        self.zoom_overlay.raise_()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Геометрия страниц вкладок известна только после показа.
        QTimer.singleShot(0, self._place_zoom)
        QTimer.singleShot(0, self.reposition_overlays)

    def reposition_overlays(self) -> None:
        """Оверлеи закреплены в углах страницы с фото."""
        self._place_zoom()
        self._place_advisory()

    def _place_advisory(self) -> None:
        """Предупреждение в правом верхнем углу страницы, левее шкалы масштаба."""
        toast = self.advisory_toast
        if toast is None or toast.isHidden():
            return
        page = self._page_rect()
        x = page.right() - self.zoom_overlay.width() - toast.width() - 20
        y = page.top() + 10
        x = max(page.left(), min(x, page.right() - toast.width()))
        y = max(page.top(), min(y, page.bottom() - toast.height()))
        toast.move(x, y)
        toast.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_zoom()
        self.reposition_overlays()

    def eventFilter(self, obj, event) -> bool:
        if self._inside(obj):
            allowed = self.can_interact is None or self.can_interact()
            if event.type() == QEvent.Type.Wheel:
                if allowed:
                    steps = event.angleDelta().y() // 120
                    if steps:
                        self.wheel_stepped.emit(steps)
                return True
        return super().eventFilter(obj, event)


class WindowMenuBar(QMenuBar):
    """Строка меню, за которую можно перетаскивать безрамочное окно."""

    def __init__(self, window: QMainWindow):
        super().__init__(window)
        self._window = window
        self._drag_pos: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.actionAt(event.position().toPoint()) is None:
                self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            current = event.globalPosition().toPoint()
            delta = current - self._drag_pos
            if delta.manhattanLength() > 4:
                self._window.move(self._window.pos() + delta)
                self._drag_pos = current
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Photo", "Photo")
        self.source_path: Path | None = None
        self.background_path: Path | None = None
        self.sliders: dict[str, tuple[QSlider, int, QLabel, str]] = {}
        self.previews: dict[str, tuple[ImagePreview, ...]] = {}
        self._worker: CoreWorker | None = None
        self._busy = False
        self._last_hint: str | None = None
        self._cut_source_path: Path | None = None
        self._composed_bg_path: Path | None = None

        self._init_ui()
        self._connect_actions()
        self._load_settings()
        self._center_on_screen()
        self._ui_ready = True

        self._log("OK", "Готово. Откройте исходное фото через Файл → Открыть исходное фото.")
        self._update_hint()

    # ---------- построение окна ----------

    def _init_ui(self) -> None:
        self.setWindowTitle("Photo — замена фона")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(800, 600)
        self.resize(1240, 820)
        self.setStyleSheet(THEMES["Тёмная"])
        self._theme_name = "Тёмная"  # для нативной шапки диалогов

        self._menu_bar = WindowMenuBar(self)
        self.setMenuBar(self._menu_bar)
        self._create_menu()
        self._create_toolbar()

        self.params_zone = self._build_params_zone()
        self.params_zone.setFixedWidth(PARAMS_WIDTH)
        self.preview_area = self._build_preview_zone()
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self.params_zone)
        top_splitter.addWidget(self.preview_area)
        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setSizes([PARAMS_WIDTH, 900])

        self.log_zone = self._build_log_zone()
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self.log_zone)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([600, 210])

        self.setCentralWidget(main_splitter)
        self.statusBar().showMessage("Готово")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_rounded_corners)

    def _create_menu(self) -> None:
        # Кнопки управления окном — справа в той же строке, что и меню.
        controls = QWidget()
        controls.setObjectName("windowControls")
        row = QHBoxLayout(controls)
        row.setContentsMargins(8, 0, 2, 0)
        row.setSpacing(2)
        for text, tip, slot in (
            ("─", "Свернуть", self.showMinimized),
            ("□", "Развернуть", self._toggle_maximize),
            ("✕", "Закрыть", self.close),
        ):
            button = QPushButton(text)
            button.setObjectName("windowButton")
            button.setToolTip(tip)
            button.setFixedSize(28, 22)
            button.clicked.connect(slot)
            row.addWidget(button)
        self.btn_maximize = row.itemAt(1).widget()
        self._menu_bar.setCornerWidget(controls, Qt.Corner.TopRightCorner)

        menu = self._menu_bar.addMenu("&Файл")
        self.act_open_source = menu.addAction("Открыть исходное фото…")
        self.act_open_source.setShortcut("Ctrl+O")
        self.act_open_background = menu.addAction("Открыть фон…")
        menu.addSeparator()
        self.act_save_result = menu.addAction("Сохранить результат (JPEG)")
        self.act_save_result.setShortcut("Ctrl+S")
        menu.addSeparator()
        self.act_exit = menu.addAction("Выход")

        self.act_settings = self._menu_bar.addAction("&Настройки")

        menu = self._menu_bar.addMenu("&Вид")

        theme_group = QActionGroup(self)
        self.act_theme_dark = menu.addAction("Тёмная тема")
        self.act_theme_dark.setCheckable(True)
        self.act_theme_dark.setActionGroup(theme_group)
        self.act_theme_light = menu.addAction("Светлая тема")
        self.act_theme_light.setCheckable(True)
        self.act_theme_light.setActionGroup(theme_group)
        self.act_theme_dark.setChecked(True)

        menu.addSeparator()
        self.act_show_params = menu.addAction("Показать панель задач")
        self.act_show_params.setCheckable(True)
        self.act_show_params.setChecked(True)
        self.act_show_toolbar = menu.addAction("Показать панель инструментов")
        self.act_show_toolbar.setCheckable(True)
        self.act_show_toolbar.setChecked(True)
        self.act_show_log = menu.addAction("Показать панель сообщений")
        self.act_show_log.setCheckable(True)
        self.act_show_log.setChecked(True)

        self.act_about = self._menu_bar.addAction("&О программе")

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.btn_maximize.setText("□")
            self.btn_maximize.setToolTip("Развернуть")
        else:
            self.showMaximized()
            self.btn_maximize.setText("❐")
            self.btn_maximize.setToolTip("Восстановить")
        self._apply_rounded_corners()

    # ---------- безрамочное окно: нативный resize и скруглённые углы ----------

    def nativeEvent(self, eventType, message):
        """Нативное растягивание: сравниваем физические координаты Windows."""
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            msg = _WinMessage.from_address(int(message))
            if msg.message == WM_NCHITTEST and not self.isMaximized():
                # lParam содержит ФИЗИЧЕСКИЕ экранные пиксели. mapFromGlobal()
                # ожидает логические, поэтому при масштабе 150–300 % зона
                # захвата уезжала внутрь окна. Берём физический rect из Windows.
                rect = wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(
                    wintypes.HWND(int(self.winId())), ctypes.byref(rect)
                )
                screen_x = ctypes.c_short(msg.lParam & 0xFFFF).value
                screen_y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                margin = max(6, round(8 * self.devicePixelRatioF()))
                horizontal = (
                    -1 if screen_x <= rect.left + margin
                    else 1 if screen_x >= rect.right - margin
                    else 0
                )
                vertical = (
                    -1 if screen_y <= rect.top + margin
                    else 1 if screen_y >= rect.bottom - margin
                    else 0
                )
                edge = _HT_EDGES.get((horizontal, vertical))
                if edge is not None:
                    return True, edge
        # В PyQt6 6.12 вызов super().nativeEvent() из override падает с
        # access violation; безопасно вернуть 「не обработано」 напрямую.
        return False, 0

    def _center_on_screen(self) -> None:
        """Размещает окно по центру рабочей области, занимая 85 % её площади."""
        screen = self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        # Площадь 85 % => линейный масшта √(0.85) ≈ 0.922 по каждой стороне.
        scale = math.sqrt(0.85)
        width = max(self.minimumWidth(), round(area.width() * scale))
        height = max(self.minimumHeight(), round(area.height() * scale))
        x = area.left() + (area.width() - width) // 2
        y = area.top() + (area.height() - height) // 2
        self.setGeometry(x, y, width, height)

    def _apply_rounded_corners(self) -> None:
        if self.isMaximized():
            self.clearMask()
            self._set_dwm_corners(False)
            return
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, self.width(), self.height()), 10, 10
        )
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        self._set_dwm_corners(True)

    def _set_dwm_corners(self, rounded: bool) -> None:
        if sys.platform != "win32":
            return
        try:
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2, DWMWCP_DEFAULT = 0
            value = ctypes.c_int(2 if rounded else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(int(self.winId())),
                33,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:  # noqa: S110 — API есть не во всех версиях Windows
            pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_rounded_corners()

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Операции")
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        def action(text: str, icon: str, tip: str) -> QAction:
            act = QAction(_icon(icon), text, self)
            act.setToolTip(tip)
            toolbar.addAction(act)
            return act

        self.tb_open_source = action("Открыть фото", "SP_DialogOpenButton", "Выбрать исходное изображение")
        self.tb_open_background = action("Выбрать фон", "SP_DialogOpenButton", "Выбрать изображение фона")
        toolbar.addSeparator()
        self.tb_cut = action("Вырезать", "SP_MediaPlay", "Вырезать объект")
        self.tb_cut.setIcon(_solid_icon("SP_MediaPlay", "#16a34a"))
        self.tb_generate = action("Сгенерировать фон", "SP_BrowserReload", "Генерация фона")
        self.tb_upscale = action("Апскейл", "SP_ArrowUp",
                                 f"Апскейл ×{self._upscale_factor()} выбранного фона")
        self.tb_upscale.setIcon(_solid_icon("SP_ArrowUp", "#0ea5e9"))
        self.tb_compose = action("Собрать", "SP_DialogApplyButton", "Собрать композит")
        toolbar.addSeparator()
        self.tb_stop = action("Стоп", "SP_BrowserStop", "Остановить операцию")
        self.tb_stop.setEnabled(False)
        self.tb_save = action("Сохранить", "SP_DialogSaveButton", "Сохранить JPEG в data\\")

    def _build_params_zone(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("zone")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        title = QLabel("ПАРАМЕТРЫ ЗАДАЧИ")
        title.setObjectName("zoneTitle")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setObjectName("paramsViewport")
        content = QWidget()
        content.setObjectName("paramsContent")
        form = QVBoxLayout(content)
        form.setContentsMargins(0, 0, 4, 0)
        form.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        source = QGroupBox("Исходное фото")
        source.setObjectName("taskSource")
        box = QVBoxLayout(source)
        self.lbl_source = self._path_label("Файл не выбран")
        box.addWidget(self.lbl_source)
        self.btn_pick_source = QPushButton(_icon("SP_DialogOpenButton"), "Выбрать…")
        box.addWidget(self.btn_pick_source)
        form.addWidget(source)

        background = QGroupBox("Фон")
        background.setObjectName("taskBackground")
        box = QVBoxLayout(background)
        self.lbl_background = self._path_label("Файл не выбран")
        box.addWidget(self.lbl_background)
        self.btn_pick_background = QPushButton(_icon("SP_DialogOpenButton"), "Выбрать…")
        box.addWidget(self.btn_pick_background)
        box.addWidget(QLabel("Промпт для генерации:"))
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText(PROMPT_PLACEHOLDER)
        self.prompt.setFixedHeight(64)
        box.addWidget(self.prompt)
        self.btn_generate = QPushButton("Сгенерировать фон")
        box.addWidget(self.btn_generate)
        form.addWidget(background)

        cut = QGroupBox("Вырезка")
        cut.setObjectName("taskCut")
        box = QVBoxLayout(cut)
        box.addWidget(QLabel("Модель:"))
        self.cut_model = QComboBox()
        self.cut_model.addItems(CUT_MODELS)
        box.addWidget(self.cut_model)
        self.portrait = QCheckBox("Портретный режим")
        box.addWidget(self.portrait)
        self.btn_cut = QPushButton("Вырезать объект")
        box.addWidget(self.btn_cut)
        form.addWidget(cut)

        compose = QGroupBox("Композит")
        compose.setObjectName("taskCompose")
        box = QVBoxLayout(compose)
        self._add_slider(box, "Размытие фона", "blur", 0, 40, 5, 10, "{:.1f}")
        self._add_slider(box, "Контактная тень", "shadow", 0, 50, 22, 100, "{:.2f}")
        self._add_slider(box, "Подгонка яркости", "tone", 80, 130, 106, 100, "{:.2f}")
        self._add_slider(box, "Зерно", "grain", 0, 120, 45, 10, "{:.1f}")
        self.btn_compose = QPushButton("Собрать композит")
        box.addWidget(self.btn_compose)
        form.addWidget(compose)

        form.addStretch()
        return frame

    def _build_preview_zone(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("zone")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("ПРЕДПРОСМОТР")
        title.setObjectName("zoneTitle")
        header = QHBoxLayout()
        header.addWidget(title)
        # Имя и разрешение активной вкладки: обновляется вместе с превью.
        self.preview_info = ElidedLabel()
        self.preview_info.setObjectName("previewInfo")
        header.addWidget(self.preview_info)
        self.btn_fit_view = QPushButton("Вписать")
        header.addWidget(self.btn_fit_view)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        for name in PREVIEW_TABS:
            widget = QWidget()
            widget.setObjectName("previewPage")
            if name == "До — После":
                inner = QHBoxLayout(widget)
                inner.setContentsMargins(6, 6, 6, 6)
                inner.setSpacing(6)
                before = ImagePreview("Исходник")
                after = ImagePreview("Результат")
                inner.addWidget(before)
                inner.addWidget(after)
                self.previews[name] = (before, after)
            else:
                inner = QVBoxLayout(widget)
                inner.setContentsMargins(6, 6, 6, 6)
                preview = ImagePreview()
                inner.addWidget(preview)
                self.previews[name] = (preview,)
            self.tabs.addTab(widget, name)

        # Кнопки очистки и сохранения — в том же ряду, что и вкладки, справа от них.
        self.btn_clear_current = QPushButton(_icon("SP_DialogDiscardButton"), "Очистить")
        self.btn_clear_current.setObjectName("clearCurrent")
        self.btn_clear_current.setToolTip("Очистить предпросмотр текущей вкладки (файлы не удаляются)")
        self.btn_clear_current.setEnabled(False)
        self.btn_save_current = QPushButton(_icon("SP_DirIcon"), "Сохранить")
        self.btn_save_current.setObjectName("saveCurrent")
        self.btn_save_current.setToolTip("Сохранить изображение текущей вкладки")
        self.btn_save_current.setEnabled(False)
        tab_buttons = QWidget()
        button_row = QHBoxLayout(tab_buttons)
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(2)
        button_row.addWidget(self.btn_clear_current)
        button_row.addWidget(self.btn_save_current)
        self.tabs.setCornerWidget(tab_buttons, Qt.Corner.TopRightCorner)

        # Вертикальная шкала кратности в правом верхнем углу изображения.
        zoom_overlay = ZoomOverlay()
        zoom_layout = QHBoxLayout(zoom_overlay)
        zoom_layout.setContentsMargins(4, 6, 4, 6)
        zoom_layout.setSpacing(2)
        labels = QVBoxLayout()
        labels.setSpacing(0)
        for value, text in ZOOM_LABELS:
            label = QLabel(text)
            label.setObjectName("zoomLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setFixedWidth(24)
            labels.addWidget(label)
            if value != ZOOM_MIN:
                labels.addStretch()
        zoom_layout.addLayout(labels)
        self.zoom_slider = QSlider(Qt.Orientation.Vertical)
        self.zoom_slider.setObjectName("zoomSlider")
        self.zoom_slider.setRange(ZOOM_MIN, ZOOM_MAX)  # -100 → ÷2, 0 → ×1, +200 → ×4
        self.zoom_slider.setValue(0)
        self.zoom_slider.setSingleStep(5)
        self.zoom_slider.setFixedHeight(120)  # та же высота, что у области подписей: метки совпадают с ручкой
        zoom_layout.addWidget(self.zoom_slider)

        # Всплывающее предупреждение о качестве вырезки — не занимает место в слое.
        advisory_toast = AdvisoryToast()
        self.advisory_toast = advisory_toast
        area = PreviewArea(self.tabs, zoom_overlay, advisory_toast)
        self.preview_area_controls = area
        layout.addWidget(area)
        return frame

    def _visible_image_rects(self) -> list[QRect]:
        """Видимые прямоугольники картинок текущей вкладки в координатах area."""
        area = self.preview_area_controls
        rects = []
        for preview in self.previews.get(self.tabs.tabText(self.tabs.currentIndex()), ()):
            rect = preview.image_rect()
            if not rect.isEmpty():
                rects.append(QRect(preview.mapTo(area, rect.topLeft()), rect.size()))
        return rects

    def _build_log_zone(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("zone")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("СЛУЖЕБНЫЕ СООБЩЕНИЯ")
        title.setObjectName("zoneTitle")
        header.addWidget(title)
        header.addStretch()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(220)
        header.addWidget(self.progress)
        self.btn_stop = QPushButton("Стоп")
        self.btn_stop.setEnabled(False)
        header.addWidget(self.btn_stop)
        layout.addLayout(header)

        self.log_display = QTextEdit()
        self.log_display.setObjectName("log")
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)
        return frame

    def _path_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("pathLabel")
        label.setWordWrap(True)
        # Путь Windows не содержит точек разрыва — minimumSizeHint() становится
        # равным всей строке (до 1200 px) и давит на splitter. Забираем размер
        # подсказку у политики: метка переносится внутри отведённой ширины.
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _add_slider(
        self,
        layout: QVBoxLayout,
        title: str,
        key: str,
        lo: int,
        hi: int,
        default: int,
        factor: int,
        fmt: str,
    ) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel(title))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(default)
        value = QLabel(fmt.format(default / factor))
        value.setFixedWidth(48)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(slider, 1)
        row.addWidget(value)
        layout.addLayout(row)
        self.sliders[key] = (slider, factor, value, fmt)
        slider.valueChanged.connect(lambda v, k=key: self._on_slider(k, v))

    # ---------- связи ----------

    def _connect_actions(self) -> None:
        self.act_open_source.triggered.connect(self.open_source)
        self.act_open_background.triggered.connect(self.open_background)
        self.act_save_result.triggered.connect(self.save_result)
        self.act_exit.triggered.connect(self.close)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_about.triggered.connect(self.open_about)

        self.act_theme_dark.triggered.connect(lambda: self._apply_theme("Тёмная"))
        self.act_theme_light.triggered.connect(lambda: self._apply_theme("Светлая"))
        self.act_show_params.toggled.connect(self._on_toggle_params)
        self.act_show_toolbar.toggled.connect(self._on_toggle_toolbar)
        self.act_show_log.toggled.connect(self._on_toggle_log)

        zoom_overlay = self.preview_area_controls.zoom_overlay
        self.preview_area_controls.can_interact = self._has_current_image
        zoom_overlay.can_reveal = self._has_current_image
        self.zoom_slider.valueChanged.connect(self._on_zoom_value)
        self.preview_area_controls.wheel_stepped.connect(zoom_overlay.reveal)
        self.preview_area_controls.wheel_stepped.connect(
            lambda steps: self.zoom_slider.setValue(
                max(ZOOM_MIN, min(ZOOM_MAX, self.zoom_slider.value() + steps * 5))
            )
        )
        self.btn_fit_view.clicked.connect(lambda: self.zoom_slider.setValue(0))
        self.tabs.currentChanged.connect(self._sync_zoom_controls)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.currentChanged.connect(self.preview_area_controls._place_zoom)
        self.tabs.currentChanged.connect(self.preview_area_controls.reposition_overlays)
        self.tabs.currentChanged.connect(self._update_preview_info)
        for previews in self.previews.values():
            for preview in previews:
                preview.moved.connect(self.preview_area_controls.reposition_overlays)
                preview.moved.connect(self._update_tab_actions)
                preview.moved.connect(self._update_preview_info)

        self.btn_clear_current.clicked.connect(self.clear_current)
        self.btn_save_current.clicked.connect(self.save_current)
        self.tabs.currentChanged.connect(self._update_tab_actions)
        self._update_tab_actions()
        self._update_preview_info()

        self.tb_open_source.triggered.connect(self.open_source)
        self.tb_open_background.triggered.connect(self.open_background)
        self.tb_cut.triggered.connect(self.run_cut)
        self.tb_generate.triggered.connect(self.run_generate)
        self.btn_generate.clicked.connect(self.run_generate)
        self.tb_upscale.triggered.connect(self.run_upscale)
        self.tb_compose.triggered.connect(self.run_compose)
        self.tb_stop.triggered.connect(self.stop_operation)
        self.tb_save.triggered.connect(self.save_result)

        self.btn_pick_source.clicked.connect(self.open_source)
        self.btn_pick_background.clicked.connect(self.open_background)
        self.btn_cut.clicked.connect(self.run_cut)
        self.btn_compose.clicked.connect(self.run_compose)
        self.btn_stop.clicked.connect(self.stop_operation)

    # ---------- действия ----------

    def _current_previews(self) -> tuple[ImagePreview, ...]:
        return self.previews.get(self.tabs.tabText(self.tabs.currentIndex()), ())

    def _has_current_image(self) -> bool:
        """Функции доступны, только если в текущей вкладке есть изображение."""
        return any(preview.source_pixmap() is not None for preview in self._current_previews())

    def _can_save_current(self) -> bool:
        """Кнопка «Сохранить» активна для промежуточных вкладок с картинкой."""
        name = self.tabs.tabText(self.tabs.currentIndex())
        if name not in SAVE_TABS:
            return False
        return all(preview.source_pixmap() is not None for preview in self.previews[name])

    def _can_clear_current(self) -> bool:
        """«Очистить» активна, когда в текущей вкладке есть что сбрасывать."""
        name = self.tabs.tabText(self.tabs.currentIndex())
        if name not in SAVE_TABS:  # исходник очищается только выбором нового файла
            return False
        if name == "Фон" and self.background_path is not None:
            return True
        return any(preview.source_pixmap() is not None for preview in self.previews[name])

    def _update_tab_actions(self, _index: int | None = None) -> None:
        """Сохранить/Очистить зависят от текущей вкладки и занятости приложения."""
        name = self.tabs.tabText(self.tabs.currentIndex())
        active = not self._busy
        self.btn_clear_current.setVisible(name in SAVE_TABS)
        self.btn_clear_current.setEnabled(active and self._can_clear_current())
        self.btn_save_current.setEnabled(active and self._can_save_current())

    def _preview_path(self, tab: str, index: int = 0) -> Path | None:
        raw = self.previews[tab][index].source_path()
        return Path(raw) if raw else None

    def _next_hint(self) -> str:
        """Один полезный совет под текущее состояние обработки."""
        source = self.source_path
        cut = self._preview_path("Вырезка")
        background = self.background_path
        result = self._preview_path("Результат")

        if not source:
            return "Откройте исходное фото (Ctrl+O) — с него начинается работа."
        if not cut:
            return "Вырежьте объект: только после этого можно заменить фон."
        if self._cut_source_path and self._cut_source_path != source:
            return "Исходник заменён после вырезки — повторите вырезку."
        if not background:
            return (
                "Выберите готовый фон или опишите его в поле запроса и нажмите "
                "«Сгенерировать фон»."
            )
        if result:
            if self._composed_bg_path and self._composed_bg_path != background:
                return "Фон изменился после сборки — соберите композит заново."
            return "Результат готов — сохраните его кнопкой «Сохранить результат» (Ctrl+S)."

        source_size = _image_size(source)
        bg_size = _image_size(background)
        if source_size and bg_size:
            sw, sh = source_size
            bw, bh = bg_size
            source_side, bg_side = max(sw, sh), max(bw, bh)
            if bg_side < source_side * 0.9:
                if background.stem.endswith(("-2x", "-4x")):
                    return (
                        f"Фон после апскейла {bw}×{bh} всё ещё меньше исходника "
                        f"{sw}×{sh} — можно повторить апскейл или оставить как есть."
                    )
                return (
                    f"Фон {bw}×{bh} меньше исходника {sw}×{sh} — сделайте апскейл "
                    f"×{self._upscale_factor()}. Размер результата останется {sw}×{sh}."
                )
            if bg_side > MAX_PREVIEW_SIDE:
                return (
                    f"Фон {bw}×{bh} больше 4096 px: в окне уменьшенное превью, файл "
                    "и «Сохранить» — полного размера. Собирайте композит."
                )
            return (
                f"Фон {bw}×{bh} не мельче исходника {sw}×{sh} — апскейл не нужен, "
                "собирайте композит."
            )
        return "Соберите композит — фон и вырезка готовы."

    def _hints_enabled(self) -> bool:
        """Подсказки в инфоокне можно отключить в Настройках → Общие."""
        return self.settings.value("ui/hints", APP_DEFAULTS["ui/hints"], type=bool)

    def _update_hint(self) -> None:
        """Писать совет в инфоокно только при изменении состояния."""
        if not self._hints_enabled():
            # При повторном включении текущий совет должен появиться заново.
            self._last_hint = None
            return
        if self._busy:
            return
        hint = self._next_hint()
        if hint == self._last_hint:
            return
        self._last_hint = hint
        self._log("HINT", hint)

    def _update_preview_info(self, *_args) -> None:
        """Имя и настоящее разрешение файлов активной вкладки в шапке зоны."""
        name = self.tabs.tabText(self.tabs.currentIndex())
        parts: list[str] = []
        tips: list[str] = []
        for preview in self.previews.get(name, ()):
            path = preview.source_path()
            if path:
                label, tip = _image_info(path)
                parts.append(label)
                tips.append(tip)
        self.preview_info.setText("  →  ".join(parts))
        self.preview_info.setToolTip("\n\n".join(tips))

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.tabText(index) != "Исходник":
            self.advisory_toast.dismiss()
        if not self._has_current_image():
            self.preview_area_controls.zoom_overlay._hide()

    def clear_current(self) -> None:
        """Сбросить предпросмотр этапа, чтобы переделать его заново.

        Файлы на диске не удаляются: сбрасывается только предпросмотр, поэтому
        в логе явно говорится, что очищено изображение вкладки.
        """
        if self._busy or not self._can_clear_current():
            return
        name = self.tabs.tabText(self.tabs.currentIndex())
        for preview in self.previews[name]:
            preview.clear_image()
        if name == "Фон":
            self.background_path = None
            self.lbl_background.setText("Файл не выбран")
        if not self._has_current_image():
            self.preview_area_controls.zoom_overlay._hide()
        self._log("OK", f"Предпросмотр «{name}» очищен. Файлы на диске не удалены.")
        self._update_tab_actions()
        self._update_hint()

    def _dialog_start_dir(self, key: str, fallback: Path) -> str:
        """Папка последнего файла; если её уже нет — стандартная папка проекта."""
        start = self.settings.value(key, "", type=str)
        if start and Path(start).is_dir():
            return start
        return str(fallback if fallback.is_dir() else DATA_DIR)

    def open_source(self) -> None:
        start = self._dialog_start_dir("paths/last_source_dir", DATA_DIR)
        path, _ = QFileDialog.getOpenFileName(self, "Открыть исходное фото", start, IMAGE_FILTER)
        if not path:
            return
        self.settings.setValue("paths/last_source_dir", str(Path(path).parent))
        self.source_path = Path(path)
        if self.previews["Исходник"][0].set_image(path):
            self.previews["До — После"][0].set_image(path)
            self.lbl_source.setText(path)
            self._log("OK", f"Исходное фото: {path}")
            self._update_source_advisory(path)
            self._update_tab_actions()
            self._activate_tab("Исходник")
            self._update_hint()
        else:
            self.source_path = None
            self._log("ERROR", f"Не удалось прочитать: {path}")
            self.advisory_toast.dismiss()
            self._update_hint()

    def open_background(self) -> None:
        start = self._dialog_start_dir("paths/last_bg_dir", BG_DIR)
        path, _ = QFileDialog.getOpenFileName(self, "Открыть фон", start, IMAGE_FILTER)
        if path:
            self.settings.setValue("paths/last_bg_dir", str(Path(path).parent))
            self._set_background(Path(path))

    def _set_background(self, path: Path, quiet: bool = False) -> bool:
        """Фон выбирается один раз: диалогом, генерацией или апскейлом."""
        if not self.previews["Фон"][0].set_image(path):
            self._log("ERROR", f"Не удалось показать фон {path}.")
            return False
        self.background_path = path
        self.lbl_background.setText(str(path))
        if not quiet:
            self._log("OK", f"Фон: {path}")
        self._update_tab_actions()
        self._activate_tab("Фон")
        self._update_hint()
        return True

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_settings()
            self.tb_upscale.setToolTip(f"Апскейл ×{self._upscale_factor()} выбранного фона")
            self._log("OK", "Настройки сохранены.")
            self._update_hint()
            if dialog.generate_requested:
                # Промпт из диалога одноразовый: переносим его в панель только
                # при запуске генерации, чтобы не затирать введённый пользователем.
                typed = dialog.prompt_text
                if typed:
                    self.prompt.setPlainText(typed)
                self.run_generate()

    def open_about(self) -> None:
        AboutDialog(self, dark=self._theme_name == "Тёмная").exec()

    def _save_preview_full(self, preview: ImagePreview, path: Path, fmt: str) -> bool:
        """Сохранить полный размер из файла; фолбэк — уменьшенное превью."""
        src = preview.source_path()
        if src and Path(src).exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            try:
                img = _read(src)
            except Exception:
                img = None
            if img is not None:
                _write(path, img)
                return True
        pixmap = preview.source_pixmap()
        return pixmap is not None and pixmap.save(str(path), fmt, 92)

    def _save_tab_full(self, tab: str, path: Path, fmt: str) -> bool:
        previews = self.previews[tab]
        if tab == "До — После":
            before, after = (p.source_path() for p in previews)
            if (before and after and Path(before).exists() and Path(after).exists()
                    and path.suffix.lower() in {".png", ".jpg", ".jpeg"}):
                try:
                    combined = _combine_full_res(before, after)
                except Exception:
                    combined = None
                if combined is not None:
                    _write(path, combined)
                    return True
            pixmap = self._combine_side_by_side(
                previews[0].source_pixmap(), previews[1].source_pixmap()
            )
            return pixmap.save(str(path), fmt, 92)
        return self._save_preview_full(previews[0], path, fmt)

    def save_result(self) -> None:
        preview = self.previews["Результат"][0]
        if preview.source_pixmap() is None:
            self._log("WARN", "Нет результата для сохранения — сначала соберите композит.")
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out = DATA_DIR / "result.jpg"
        if self._save_preview_full(preview, out, "JPG"):
            self._log("OK", f"JPEG сохранён: {out}")
            self.statusBar().showMessage(f"Сохранено: {out}", 5000)
        else:
            self._log("ERROR", f"Не удалось сохранить: {out}")

    @staticmethod
    def _combine_side_by_side(before: QPixmap, after: QPixmap) -> QPixmap:
        """Сложить половинки «До — После» в одно изображение."""
        height = max(before.height(), after.height())

        def fit(pixmap: QPixmap) -> QPixmap:
            if not pixmap.height():
                return pixmap
            width = round(pixmap.width() * height / pixmap.height())
            return pixmap.scaled(
                width, height, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        left, right = fit(before), fit(after)
        gap = 6
        combined = QPixmap(left.width() + gap + right.width(), height)
        combined.fill(Qt.GlobalColor.white)
        painter = QPainter(combined)
        painter.drawPixmap(0, 0, left)
        painter.drawPixmap(left.width() + gap, 0, right)
        painter.end()
        return combined

    def save_current(self) -> None:
        """Сохранить изображение текущей вкладки через диалог выбора файла."""
        if self._busy or not self._can_save_current():
            return
        tab = self.tabs.tabText(self.tabs.currentIndex())
        default_name, filters = SAVE_PRESETS[tab]
        start = Path(self._dialog_start_dir("paths/last_save_dir", DATA_DIR)) / default_name
        chosen, _ = QFileDialog.getSaveFileName(self, f"Сохранить: {tab}", str(start), filters)
        if not chosen:
            return
        path = Path(chosen)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            path = path.with_suffix(".png" if tab == "Вырезка" else ".jpg")
        if tab == "Вырезка" and path.suffix.lower() != ".png":
            self._log("WARN", "JPEG не сохраняет прозрачность — для вырезки лучше PNG.")
        if all(p.source_pixmap() is None for p in self.previews[tab]):
            self._log("WARN", f"Нечего сохранять во вкладке «{tab}».")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt = "PNG" if path.suffix.lower() == ".png" else "JPG"
        if self._save_tab_full(tab, path, fmt):
            self.settings.setValue("paths/last_save_dir", str(path.parent))
            self._log("OK", f"Сохранено ({tab}): {path}")
            self.statusBar().showMessage(f"Сохранено: {path}", 5000)
        else:
            self._log("ERROR", f"Не удалось сохранить: {path}")

    def _on_zoom_value(self, value: int) -> None:
        if not self._has_current_image():
            blocker = QSignalBlocker(self.zoom_slider)
            self.zoom_slider.setValue(0)
            blocker.unblock()
            return
        self._set_zoom_percent(value)
        if getattr(self, "_ui_ready", False):
            self.preview_area_controls.zoom_overlay.reveal()

    def _set_zoom_percent(self, value: int) -> None:
        """Кратность к вписанному кадру: −100 → ÷2, 0 → ×1, +200 → ×4."""
        if not self._has_current_image():
            return
        for preview in self.previews.get(self.tabs.tabText(self.tabs.currentIndex()), ()):
            if preview.source_pixmap() is None:
                continue
            if value == 0:
                preview.set_zoom(0.0)
            else:
                preview.set_zoom(preview.fit_factor() * (2 ** (value / 100.0)))

    def _sync_zoom_controls(self) -> None:
        previews = self.previews.get(self.tabs.tabText(self.tabs.currentIndex()), ())
        if not previews:
            return
        preview = previews[0]
        zoom = preview.zoom
        if zoom == 0.0:
            value = 0
        else:
            factor = preview.fit_factor()
            value = round(math.log2(zoom / factor) * 100) if factor > 0 and zoom > 0 else 0
        blocker = QSignalBlocker(self.zoom_slider)
        self.zoom_slider.setValue(max(ZOOM_MIN, min(ZOOM_MAX, value)))
        blocker.unblock()

    def _apply_theme(self, name: str) -> None:
        if name not in THEMES:
            name = "Тёмная"
        self._theme_name = name
        self.setStyleSheet(THEMES[name])
        self.act_theme_dark.setChecked(name == "Тёмная")
        self.act_theme_light.setChecked(name == "Светлая")
        self.settings.setValue("ui/theme", name)

    def _on_toggle_params(self, checked: bool) -> None:
        self.params_zone.setVisible(checked)
        self.settings.setValue("ui/show_params", checked)

    def _on_toggle_toolbar(self, checked: bool) -> None:
        self.toolbar.setVisible(checked)
        self.settings.setValue("ui/show_toolbar", checked)

    def _on_toggle_log(self, checked: bool) -> None:
        self.log_zone.setVisible(checked)
        self.settings.setValue("ui/show_log", checked)

    def _on_slider(self, key: str, value: int) -> None:
        _slider, factor, label, fmt = self.sliders[key]
        label.setText(fmt.format(value / factor))

    # ---------- фоновые операции ----------

    def run_cut(self) -> None:
        params = self.current_params()
        if not params["source"]:
            self._log("WARN", "Вырезка: сначала откройте исходное фото.")
            return
        self._start_worker(
            "Вырезка", cut_task, params["source"],
            options={
                "portrait": params["portrait"],
                "model": params["cut_model"],
                "tile": params["cut_tile"],
                "sigma": params["cut_sigma"],
                "head_ratio": params["cut_head_ratio"],
                "matting": params["cut_matting"],
            },
        )

    def run_generate(self) -> None:
        params = self.current_params()
        prompt = str(params["prompt"]).strip()
        if not prompt:
            self._log("WARN", "Генерация фона: введите промпт в панели параметров.")
            return
        self._start_worker(
            "Генерация фона", genbg_task, prompt,
            options={
                "provider": params["provider"],
                "seed": params["bg_seed"],
                "size": params["bg_size"],
            },
        )

    def run_upscale(self) -> None:
        params = self.current_params()
        if not params["background"]:
            self._log("WARN", "Апскейл: сначала выберите фон.")
            return
        self._start_worker(
            "Апскейл", upscale_task, params["background"],
            options={"factor": self._upscale_factor()},
        )

    def run_compose(self) -> None:
        params = self.current_params()
        if not params["source"] or not params["background"]:
            self._log("WARN", "Сборка композита: нужны исходное фото и фон.")
            return
        if not Path(CUTOUT_FILE).exists():
            self._log("WARN", "Сборка композита: сначала вырежьте объект.")
            return
        self._start_worker(
            "Сборка композита", compose_task, str(CUTOUT_FILE), params["background"],
            options={
                "blur": params["blur"],
                "shadow": params["shadow"],
                "tone": params["tone"],
                "grain": params["grain"],
                "seed": params["compose_seed"],
            },
        )

    def stop_operation(self) -> None:
        if self._worker is None or not self._worker.isRunning():
            self._log("INFO", "Операция не запущена — останавливать нечего.")
            return
        self._worker.cancel()
        self._log("WARN", "Отмена запрошена — операция остановится на следующем этапе.")

    def _start_worker(self, name: str, func, *args, **kwargs) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._log("WARN", f"«{name}» не запущена: выполняется другая операция.")
            return
        worker = CoreWorker(func, *args, **kwargs)
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.succeeded.connect(lambda result, n=name: self._on_operation_success(n, result))
        worker.failed.connect(lambda message, n=name: self._on_operation_failed(n, message))
        worker.cancelled.connect(lambda n=name: self._on_operation_cancelled(n))
        worker.finished.connect(self._on_worker_finished)
        self._set_busy(True)
        self._log("INFO", f"{name}: запуск…")
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.tb_cut, self.tb_generate, self.tb_upscale, self.tb_compose,
            self.tb_save, self.act_save_result, self.btn_cut, self.btn_generate,
            self.btn_compose,
        ):
            widget.setEnabled(not busy)
        self._busy = busy
        self._update_tab_actions()
        self.btn_stop.setEnabled(busy)
        self.tb_stop.setEnabled(busy)
        if busy:
            self.progress.setRange(0, 0)  # неопределённый режим до первого отчёта
            self.progress.setValue(0)
        elif self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self._update_hint()

    def _on_progress(self, percent: int, message: str) -> None:
        if percent < 0:
            self.progress.setRange(0, 0)
        else:
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, percent)))
        if message:
            self.statusBar().showMessage(message)

    def _on_operation_success(self, name: str, result) -> None:
        path = Path(str(result))
        if name == "Вырезка":
            ok = self._show_preview("Вырезка", path)
            self._cut_source_path = self.source_path
            self._activate_tab("Вырезка")
        elif name in ("Генерация фона", "Апскейл"):
            ok = self._set_background(path, quiet=True)  # сам открывает вкладку «Фон»
            # Показываем после смены вкладки: _on_tab_changed гасит старый тост.
            if ok:
                self._warn_preview_downscale(path)
        elif name == "Сборка композита":
            ok_result = self._show_preview("Результат", path)
            ok_before = self._show_preview("До — После", path, 1)
            ok = ok_result and ok_before
            self._composed_bg_path = self.background_path
            self._activate_tab("Результат")
        else:
            ok = True
        # Файл записан, но превью мог не открыться — не выдавать это за успех.
        if ok:
            self._log("OK", f"{name}: {path}")
        self._update_hint()

    def _on_operation_failed(self, name: str, message: str) -> None:
        self._log("ERROR", f"{name}: {message}")

    def _on_operation_cancelled(self, name: str) -> None:
        self._log("WARN", f"{name}: отменено.")

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._set_busy(False)
        self.statusBar().showMessage("Готово", 3000)
        self._worker = None
        if worker is not None:
            worker.deleteLater()

    def _show_preview(self, tab: str, path: Path, index: int = 0) -> bool:
        preview = self.previews[tab][index]
        ok = preview.set_image(path)
        if not ok:
            self._log("ERROR", f"Не удалось показать {path} во вкладке «{tab}».")
        self._update_tab_actions()
        return ok

    def _activate_tab(self, name: str) -> None:
        """Сделать вкладку текущей, если она уже не открыта."""
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                if self.tabs.currentIndex() != index:
                    self.tabs.setCurrentIndex(index)
                return

    def _update_source_advisory(self, path: str | Path | None) -> None:
        """Всплывающее предупреждение и записи в лог о качестве вырезки."""
        if path is None:
            self.advisory_toast.dismiss()
            return
        try:
            notes = cut_advisory(path)
        except Exception as exc:  # плохой файл не должен ломать открытие
            LOG.warning("не удалось оценить кадр: %s", exc)
            notes = []
        if not notes:
            self.advisory_toast.dismiss()
            return
        for note in notes:
            self._log("WARN", note)
        self.advisory_toast.show_notes(notes)
        self.preview_area_controls.reposition_overlays()

    def _warn_preview_downscale(self, path: Path) -> None:
        """Честно сообщить, что превью уменьшено, а файл — полного размера."""
        sizes = _preview_downscale(path)
        if sizes is None:
            return
        (old_w, old_h), (new_w, new_h) = sizes
        note = (
            f"Превью уменьшено: {old_w}×{old_h} → {new_w}×{new_h} для отображения. "
            "Файл на диске и «Сохранить» — полного размера."
        )
        self._log("WARN", note)
        self.advisory_toast.show_notes([note])
        self.preview_area_controls.reposition_overlays()

    def _log(self, level: str, message: str) -> None:
        color = LEVEL_COLORS.get(level, "#e2e8f0")
        self.log_display.append(
            f'<span style="color:{color}"><b>[{level}]</b></span> {html.escape(str(message))}'
        )
        self.log_display.ensureCursorVisible()

    # ---------- настройки ----------

    def _load_settings(self) -> None:
        s = self.settings
        index = self.cut_model.findText(str(s.value("cut/model", APP_DEFAULTS["cut/model"])))
        if index >= 0:
            self.cut_model.setCurrentIndex(index)
        self.portrait.setChecked(s.value("cut/portrait", APP_DEFAULTS["cut/portrait"], type=bool))
        # Промпт намеренно не восстанавливается: поле начинается пустым с подсказкой.
        # Ползунки хранят масштабированные целые, а диалог настроек —
        # вещественные значения. Приводим к одному формату на чтении.
        defaults = {
            "blur": APP_DEFAULTS["compose/blur"],
            "shadow": APP_DEFAULTS["compose/shadow"],
            "tone": APP_DEFAULTS["compose/tone"],
            "grain": APP_DEFAULTS["compose/grain"],
        }
        for key, default in defaults.items():
            raw = s.value(f"compose/{key}", default)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = default
            slider, factor, _, _ = self.sliders[key]
            slider.setValue(round(value * factor))
        self._apply_theme(str(s.value("ui/theme", "Тёмная")))
        for action, key, widget in (
            (self.act_show_params, "ui/show_params", self.params_zone),
            (self.act_show_toolbar, "ui/show_toolbar", self.toolbar),
            (self.act_show_log, "ui/show_log", self.log_zone),
        ):
            visible = s.value(key, True, type=bool)
            blocker = QSignalBlocker(action)
            action.setChecked(visible)
            blocker.unblock()
            widget.setVisible(visible)

        self.zoom_slider.setValue(0)
        self._sync_zoom_controls()

    def _upscale_factor(self) -> int:
        """Кратность ручного апскейла: 2 — EDSR, 4 — Real-ESRGAN."""
        return normalize_factor(
            self.settings.value("upscale/factor", APP_DEFAULTS["upscale/factor"])
        )

    def _setting_number(self, key: str, default, cast):
        try:
            return cast(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def current_params(self) -> dict:
        """Параметры задачи для воркеров: UI, ползунки и раздел настроек."""
        params = {
            "cut_model": self.cut_model.currentText(),
            "portrait": self.portrait.isChecked(),
            "prompt": self.prompt.toPlainText(),
            "source": str(self.source_path) if self.source_path else None,
            "background": str(self.background_path) if self.background_path else None,
            "provider": str(self.settings.value("bg/provider_api", APP_DEFAULTS["bg/provider_api"])),
            "bg_seed": self._setting_number("bg/seed", APP_DEFAULTS["bg/seed"], int),
            "bg_size": str(self.settings.value("bg/size", APP_DEFAULTS["bg/size"])),
            "cut_tile": self._setting_number("cut/tile", APP_DEFAULTS["cut/tile"], int),
            "cut_sigma": self._setting_number("cut/sigma", APP_DEFAULTS["cut/sigma"], float),
            "cut_head_ratio": self._setting_number("cut/head_ratio", APP_DEFAULTS["cut/head_ratio"], float),
            "cut_matting": bool(self.settings.value("cut/matting", APP_DEFAULTS["cut/matting"], type=bool)),
            "compose_seed": self._setting_number("compose/seed", APP_DEFAULTS["compose/seed"], int),
            "upscale_factor": self._upscale_factor(),
        }
        for key, (slider, factor, _, _) in self.sliders.items():
            params[key] = slider.value() / factor
        return params
