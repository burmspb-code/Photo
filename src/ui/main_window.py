"""Скелет главного окна приложения замены фона.

Три зоны:
    1. меню + тулбар;
    2. результат: параметры задачи слева, предпросмотр с вкладками справа;
    3. служебные сообщения: прогресс, кнопка «Стоп», лог.

Тяжёлые операции (вырезка, генерация, апскейл, композит) пока заглушены.
Открытие файлов, предпросмотр и сохранение кадра работают по-настоящему.
"""
from __future__ import annotations

import ctypes
import html
import logging
import math
import sys
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import (
    Qt,
    QEvent,
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
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
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

from .settings_dialog import SettingsDialog
from .styles import THEMES

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
BG_DIR = DATA_DIR / "bg"

LOG = logging.getLogger(__name__)

PREVIEW_TABS = ("Исходник", "Вырезка", "Фон", "Результат", "До — После")
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


class ImagePreview(QLabel):
    """Превью с масштабированием и панорамированием перетаскиванием."""

    moved = pyqtSignal()

    def __init__(self, placeholder: str = "Изображение не загружено"):
        super().__init__(placeholder)
        self._source: QPixmap | None = None
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
        image = QImage(str(path))
        if image.isNull():
            self.clear_image("Не удалось прочитать изображение")
            return False
        self._source = QPixmap.fromImage(image)
        self._reset_view()
        self._rescale()
        self.moved.emit()
        return True

    def clear_image(self, text: str | None = None) -> None:
        self._source = None
        self._scaled = None
        self._drag_origin = None
        self.unsetCursor()
        self.setText(text or self.placeholder)
        self.update()
        self.moved.emit()

    def source_pixmap(self) -> QPixmap | None:
        """Оригинальное изображение — для сохранения результата."""
        return self._source

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
    """Вертикальная шкала 0–100% с подписями."""

    def __init__(self):
        super().__init__("zoomBar")
        self.setToolTip("Ползунок или колесо мыши — масштаб")


class NavOverlay(HoverOverlay):
    hover_stepped = pyqtSignal(int)

    def __init__(self):
        super().__init__("navBar")
        self._region = 0
        self.setToolTip("Боковые кнопки мыши или наведение на стрелку — смена кадра")

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._region = -1 if event.position().x() < self.width() / 2 else 1
        self.hover_stepped.emit(self._region)

    def mouseMoveEvent(self, event) -> None:
        region = -1 if event.position().x() < self.width() / 2 else 1
        if region != self._region:
            self._region = region
            self.hover_stepped.emit(region)
        super().mouseMoveEvent(event)


class PreviewArea(QFrame):
    """Область вкладок с наложенными прозрачными панелями управления."""

    prev_requested = pyqtSignal()
    next_requested = pyqtSignal()
    wheel_stepped = pyqtSignal(int)

    def __init__(self, tabs: QTabWidget, zoom_overlay: ZoomOverlay, nav_overlay: NavOverlay):
        super().__init__()
        self.setObjectName("previewArea")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)

        self.tabs = tabs
        self.zoom_overlay = zoom_overlay
        self.nav_overlay = nav_overlay
        self.can_interact: callable | None = None  # callable -> bool, есть ли загруженное фото
        self.image_rect_provider = None  # callable -> list[QRect] в координатах area
        for overlay in (zoom_overlay, nav_overlay):
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
        """Оба оверлея закреплены в углах страницы с фото."""
        self._place_zoom()
        page = self._page_rect()
        nx = page.left() + (page.width() - self.nav_overlay.width()) // 2
        ny = page.bottom() - self.nav_overlay.height() - 10
        nx = max(page.left(), min(nx, page.right() - self.nav_overlay.width()))
        ny = max(page.top(), min(ny, page.bottom() - self.nav_overlay.height()))
        self.nav_overlay.move(nx, ny)
        self.nav_overlay.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_zoom()
        self.reposition_overlays()

    def eventFilter(self, obj, event) -> bool:
        if self._inside(obj):
            allowed = self.can_interact is None or self.can_interact()
            if event.type() == QEvent.Type.MouseButtonPress:
                button = event.button()
                if button in (Qt.MouseButton.XButton1, Qt.MouseButton.XButton2):
                    if allowed:
                        (self.prev_requested if button == Qt.MouseButton.XButton1
                         else self.next_requested).emit()
                    return True
            elif event.type() == QEvent.Type.Wheel:
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

        self._init_ui()
        self._connect_actions()
        self._load_settings()
        self._center_on_screen()
        self._ui_ready = True

        self._log("OK", "Скелет окна готов. Откройте исходное фото через Файл → Открыть исходное фото.")

    # ---------- построение окна ----------

    def _init_ui(self) -> None:
        self.setWindowTitle("Photo — замена фона (скелет)")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(800, 600)
        self.resize(1240, 820)
        self.setStyleSheet(THEMES["Тёмная"])

        self._menu_bar = WindowMenuBar(self)
        self.setMenuBar(self._menu_bar)
        self._create_menu()
        self._create_toolbar()

        self.params_zone = self._build_params_zone()
        self.preview_area = self._build_preview_zone()
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self.params_zone)
        top_splitter.addWidget(self.preview_area)
        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setSizes([340, 900])

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
        self.tb_cut = action("Вырезать", "SP_MediaPlay", "Вырезать объект (пока заглушка)")
        self.tb_cut.setIcon(_solid_icon("SP_MediaPlay", "#16a34a"))
        self.tb_generate = action("Сгенерировать фон", "SP_BrowserReload", "Генерация фона (пока заглушка)")
        self.tb_upscale = action("Апскейл", "SP_ArrowUp", "Апскейл ×4 (пока заглушка)")
        self.tb_upscale.setIcon(_solid_icon("SP_ArrowUp", "#0ea5e9"))
        self.tb_compose = action("Собрать", "SP_DialogApplyButton", "Собрать композит (пока заглушка)")
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
        self.prompt.setFixedHeight(64)
        box.addWidget(self.prompt)
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
        header.addStretch()
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

        # Вертикальная шкала 0–100% с цифрами в правом верхнем углу изображения.
        zoom_overlay = ZoomOverlay()
        zoom_layout = QHBoxLayout(zoom_overlay)
        zoom_layout.setContentsMargins(6, 6, 6, 6)
        zoom_layout.setSpacing(2)
        labels = QVBoxLayout()
        labels.setSpacing(0)
        for value in (100, 50, 0, -50, -100):
            label = QLabel(str(value))
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setFixedWidth(30)
            labels.addWidget(label)
            if value != -100:
                labels.addStretch()
        zoom_layout.addLayout(labels)
        self.zoom_slider = QSlider(Qt.Orientation.Vertical)
        self.zoom_slider.setRange(-100, 100)  # 0 = исходный масштаб (вписать)
        self.zoom_slider.setValue(0)
        self.zoom_slider.setSingleStep(5)
        self.zoom_slider.setFixedHeight(140)
        zoom_layout.addWidget(self.zoom_slider)

        # Минимальная навигация: только две стрелки внизу изображения.
        nav_overlay = NavOverlay()
        nav_layout = QHBoxLayout(nav_overlay)
        nav_layout.setContentsMargins(6, 4, 6, 4)
        nav_layout.setSpacing(4)
        self.btn_prev_bg = QPushButton("◀")
        self.btn_prev_bg.setFixedWidth(30)
        self.btn_next_bg = QPushButton("▶")
        self.btn_next_bg.setFixedWidth(30)
        nav_layout.addWidget(self.btn_prev_bg)
        nav_layout.addWidget(self.btn_next_bg)

        area = PreviewArea(self.tabs, zoom_overlay, nav_overlay)
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

        self.act_theme_dark.triggered.connect(lambda: self._apply_theme("Тёмная"))
        self.act_theme_light.triggered.connect(lambda: self._apply_theme("Светлая"))
        self.act_show_params.toggled.connect(self._on_toggle_params)
        self.act_show_toolbar.toggled.connect(self._on_toggle_toolbar)
        self.act_show_log.toggled.connect(self._on_toggle_log)

        zoom_overlay = self.preview_area_controls.zoom_overlay
        nav_overlay = self.preview_area_controls.nav_overlay
        self.preview_area_controls.can_interact = self._has_current_image
        zoom_overlay.can_reveal = self._has_current_image
        nav_overlay.can_reveal = self._has_current_image
        self.zoom_slider.valueChanged.connect(self._on_zoom_value)
        self.preview_area_controls.wheel_stepped.connect(zoom_overlay.reveal)
        self.preview_area_controls.wheel_stepped.connect(
            lambda steps: self.zoom_slider.setValue(
                max(-100, min(100, self.zoom_slider.value() + steps * 5))
            )
        )
        self.btn_fit_view.clicked.connect(lambda: self.zoom_slider.setValue(0))
        self.tabs.currentChanged.connect(self._sync_zoom_controls)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.currentChanged.connect(self.preview_area_controls._place_zoom)
        self.tabs.currentChanged.connect(self.preview_area_controls.reposition_overlays)
        for previews in self.previews.values():
            for preview in previews:
                preview.moved.connect(self.preview_area_controls.reposition_overlays)

        self.btn_prev_bg.clicked.connect(nav_overlay.reveal)
        self.btn_next_bg.clicked.connect(nav_overlay.reveal)
        self.btn_prev_bg.clicked.connect(lambda: self._cycle_background(-1))
        self.btn_next_bg.clicked.connect(lambda: self._cycle_background(1))
        self.preview_area_controls.prev_requested.connect(nav_overlay.reveal)
        self.preview_area_controls.next_requested.connect(nav_overlay.reveal)
        self.preview_area_controls.prev_requested.connect(lambda: self._cycle_background(-1))
        self.preview_area_controls.next_requested.connect(lambda: self._cycle_background(1))
        self.preview_area_controls.nav_overlay.hover_stepped.connect(nav_overlay.reveal)
        self.preview_area_controls.nav_overlay.hover_stepped.connect(
            lambda direction: self._cycle_background(direction)
        )

        self.tb_open_source.triggered.connect(self.open_source)
        self.tb_open_background.triggered.connect(self.open_background)
        self.tb_cut.triggered.connect(lambda: self._stub("Вырезка"))
        self.tb_generate.triggered.connect(lambda: self._stub("Генерация фона"))
        self.tb_upscale.triggered.connect(lambda: self._stub("Апскейл"))
        self.tb_compose.triggered.connect(lambda: self._stub("Сборка композита"))
        self.tb_stop.triggered.connect(lambda: self._log("INFO", "Операция не запущена — останавливать нечего."))
        self.tb_save.triggered.connect(self.save_result)

        self.btn_pick_source.clicked.connect(self.open_source)
        self.btn_pick_background.clicked.connect(self.open_background)
        self.btn_cut.clicked.connect(lambda: self._stub("Вырезка"))
        self.btn_compose.clicked.connect(lambda: self._stub("Сборка композита"))

    # ---------- действия ----------

    def _current_previews(self) -> tuple[ImagePreview, ...]:
        return self.previews.get(self.tabs.tabText(self.tabs.currentIndex()), ())

    def _has_current_image(self) -> bool:
        """Функции доступны, только если в текущей вкладке есть изображение."""
        return any(preview.source_pixmap() is not None for preview in self._current_previews())

    def _on_tab_changed(self, index: int) -> None:
        if not self._has_current_image():
            area = self.preview_area_controls
            area.zoom_overlay._hide()
            area.nav_overlay._hide()

    def open_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Открыть исходное фото", str(DATA_DIR), IMAGE_FILTER)
        if not path:
            return
        self.source_path = Path(path)
        if self.previews["Исходник"][0].set_image(path):
            self.previews["До — После"][0].set_image(path)
            self.lbl_source.setText(path)
            self._log("OK", f"Исходное фото: {path}")
        else:
            self._log("ERROR", f"Не удалось прочитать: {path}")

    def open_background(self) -> None:
        start = str(BG_DIR) if BG_DIR.exists() else str(DATA_DIR)
        path, _ = QFileDialog.getOpenFileName(self, "Открыть фон", start, IMAGE_FILTER)
        if path:
            self._set_background(Path(path))

    def _set_background(self, path: Path) -> None:
        if self.previews["Фон"][0].set_image(path):
            self.background_path = path
            self.lbl_background.setText(str(path))
            self._log("OK", f"Фон: {path}")

    def _bg_files(self) -> list[Path]:
        if not BG_DIR.exists():
            return []
        return sorted(
            p for p in BG_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )

    def _cycle_background(self, delta: int) -> None:
        if not self._has_current_image():
            return
        files = self._bg_files()
        if not files:
            self._log("WARN", "В data\\bg нет изображений для перебора.")
            return
        index = files.index(self.background_path) if self.background_path in files else -1
        self._set_background(files[(index + delta) % len(files)])

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_settings()
            self._log("OK", "Настройки сохранены.")

    def save_result(self) -> None:
        preview = self.previews["Результат"][0]
        pixmap = preview.source_pixmap()
        if pixmap is None:
            self._log("WARN", "Нет результата для сохранения — сначала соберите композит.")
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out = DATA_DIR / "result.jpg"
        if pixmap.save(str(out), "JPG", 92):
            self._log("OK", f"JPEG сохранён: {out}")
            self.statusBar().showMessage(f"Сохранено: {out}", 5000)
        else:
            self._log("ERROR", f"Не удалось сохранить: {out}")

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
        """0 — исходный масштаб (вписать), −100 / +100 — вдвое меньше/больше."""
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
        self.zoom_slider.setValue(max(-100, min(100, value)))
        blocker.unblock()

    def _apply_theme(self, name: str) -> None:
        if name not in THEMES:
            name = "Тёмная"
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

    def _stub(self, name: str) -> None:
        self._log("INFO", f"«{name}» — заглушка скелета, операция ещё не подключена к core.")

    def _log(self, level: str, message: str) -> None:
        color = LEVEL_COLORS.get(level, "#e2e8f0")
        self.log_display.append(
            f'<span style="color:{color}"><b>[{level}]</b></span> {html.escape(str(message))}'
        )
        self.log_display.ensureCursorVisible()

    # ---------- настройки ----------

    def _load_settings(self) -> None:
        s = self.settings
        index = self.cut_model.findText(str(s.value("cut/model", CUT_MODELS[0])))
        if index >= 0:
            self.cut_model.setCurrentIndex(index)
        self.portrait.setChecked(s.value("cut/portrait", True, type=bool))
        self.prompt.setPlainText(
            str(s.value("bg/prompt", "realistic photo, no people, no text, soft overcast light"))
        )
        # Ползунки хранят масштабированные целые, а диалог настроек —
        # вещественные значения. Приводим к одному формату на чтении.
        defaults = {"blur": 0.5, "shadow": 0.22, "tone": 1.06, "grain": 4.5}
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

    def current_params(self) -> dict:
        """Текущие параметры задачи — понадобятся воркерам после подключения core."""
        params = {
            "cut_model": self.cut_model.currentText(),
            "portrait": self.portrait.isChecked(),
            "prompt": self.prompt.toPlainText(),
            "source": str(self.source_path) if self.source_path else None,
            "background": str(self.background_path) if self.background_path else None,
        }
        for key, (slider, factor, _, _) in self.sliders.items():
            params[key] = slider.value() / factor
        return params
