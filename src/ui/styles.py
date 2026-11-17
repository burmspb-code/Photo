"""QSS-темы GUI. Одна шаблонная таблица и две палитры: тёмная и светлая."""

from string import Template

_DARK = {
    "window": "#0f172a",
    "text": "#e2e8f0",
    "zone_bg": "#1e293b",
    "zone_border": "#334155",
    "title": "#94a3b8",
    "group_text": "#cbd5e1",
    "path_text": "#cbd5e1",
    "preview_bg": "#0b1220",
    "preview_border": "#334155",
    "preview_placeholder": "#64748b",
    "menu_bg": "#0f172a",
    "menu_selected": "#334155",
    "menu_popup": "#1e293b",
    "toolbar_bg": "#0f172a",
    "button_bg": "#1e293b",
    "button_border": "#475569",
    "button_hover": "#334155",
    "disabled": "#64748b",
    "accent": "#3b82f6",
    "accent_text": "#ffffff",
    "tab_bg": "#1e293b",
    "tab_text": "#94a3b8",
    "log_bg": "#020617",
    "log_text": "#94a3b8",
    "input_bg": "#0b1220",
    "input_border": "#475569",
    "selection": "#3b82f6",
    "slider_groove": "#334155",
    "progress_bg": "#0b1220",
    "progress_border": "#334155",
    "scroll_bg": "#0f172a",
    "scroll_handle": "#475569",
    "status_bg": "#0f172a",
    "status_text": "#94a3b8",
    "overlay_bg": "#1e293b",
    "overlay_border": "#475569",
    "overlay_text": "#cbd5e1",
}

_LIGHT = {
    "window": "#f1f5f9",
    "text": "#0f172a",
    "zone_bg": "#ffffff",
    "zone_border": "#cbd5e1",
    "title": "#475569",
    "group_text": "#334155",
    "path_text": "#334155",
    "preview_bg": "#e2e8f0",
    "preview_border": "#cbd5e1",
    "preview_placeholder": "#64748b",
    "menu_bg": "#f8fafc",
    "menu_selected": "#dbeafe",
    "menu_popup": "#ffffff",
    "toolbar_bg": "#f8fafc",
    "button_bg": "#ffffff",
    "button_border": "#cbd5e1",
    "button_hover": "#e2e8f0",
    "disabled": "#94a3b8",
    "accent": "#2563eb",
    "accent_text": "#ffffff",
    "tab_bg": "#e2e8f0",
    "tab_text": "#475569",
    "log_bg": "#ffffff",
    "log_text": "#334155",
    "input_bg": "#ffffff",
    "input_border": "#cbd5e1",
    "selection": "#2563eb",
    "slider_groove": "#cbd5e1",
    "progress_bg": "#ffffff",
    "progress_border": "#cbd5e1",
    "scroll_bg": "#f1f5f9",
    "scroll_handle": "#cbd5e1",
    "status_bg": "#f8fafc",
    "status_text": "#475569",
    "overlay_bg": "rgba(255, 255, 255, 235)",
    "overlay_border": "#cbd5e1",
    "overlay_text": "#334155",
}

_STYLE = Template(
    """
QMainWindow, QDialog {
    background: $window;
}
QWidget {
    color: $text;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 12px;
}
QFrame#zone {
    background: $zone_bg;
    border: 1px solid $zone_border;
    border-radius: 8px;
}
QLabel#zoneTitle {
    color: $title;
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 1px;
}
QLabel#pathLabel {
    color: $path_text;
}
QLabel#preview {
    background: $preview_bg;
    border: 1px solid $preview_border;
    border-radius: 6px;
    color: $preview_placeholder;
}
QFrame#previewArea {
    background: $preview_bg;
    border: 0;
}
QFrame#zoomBar, QFrame#navBar {
    background: $overlay_bg;
    border: 1px solid $overlay_border;
    border-radius: 6px;
    color: $overlay_text;
}
QFrame#zoomBar QLabel, QFrame#navBar QLabel {
    color: $overlay_text;
}
QFrame#zoomBar QPushButton, QFrame#navBar QPushButton {
    padding: 2px 6px;
}
QScrollArea {
    background: $zone_bg;
    border: 0;
}
QWidget#paramsViewport, QWidget#paramsContent {
    background: $zone_bg;
}
QWidget#previewPage {
    background: $preview_bg;
}
QGroupBox {
    background: $zone_bg;
    border: 1px solid $zone_border;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
    color: $group_text;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QMenuBar {
    background: $menu_bg;
    color: $text;
    padding: 2px 4px;
}
QMenuBar::item:selected {
    background: $menu_selected;
    border-radius: 4px;
}
QWidget#windowControls {
    background: $menu_bg;
}
QPushButton#windowButton {
    background: transparent;
    border: 0;
    padding: 0;
    color: $title;
    font-size: 14px;
}
QPushButton#windowButton:hover {
    background: $menu_selected;
    border-radius: 4px;
}
QMenu {
    background: $menu_popup;
    border: 1px solid $zone_border;
    padding: 4px;
}
QMenu::item {
    padding: 6px 22px;
}
QMenu::item:selected {
    background: $accent;
    color: $accent_text;
    border-radius: 4px;
}
QToolBar {
    background: $toolbar_bg;
    border: 0;
    spacing: 4px;
    padding: 4px;
}
QToolButton {
    background: $button_bg;
    border: 1px solid $button_border;
    border-radius: 6px;
    padding: 5px 9px;
    color: $text;
}
QToolButton:hover {
    background: $button_hover;
}
QToolButton:pressed {
    background: $accent;
    color: $accent_text;
}
QToolButton:disabled {
    color: $disabled;
    border-color: $zone_bg;
}
QPushButton {
    background: $button_bg;
    border: 1px solid $button_border;
    border-radius: 6px;
    padding: 7px 12px;
    color: $text;
}
QPushButton:hover {
    background: $button_hover;
}
QPushButton:disabled {
    color: $disabled;
}
QTabWidget::pane {
    border: 1px solid $zone_border;
    border-radius: 6px;
    background: $preview_bg;
    top: -1px;
}
QTabBar::tab {
    background: $tab_bg;
    border: 1px solid $zone_border;
    padding: 7px 14px;
    color: $tab_text;
}
QTabBar::tab:first {
    border-top-left-radius: 6px;
}
QTabBar::tab:last {
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: $accent;
    border-color: $accent;
    color: $accent_text;
    font-weight: bold;
}
QTextEdit#log {
    background: $log_bg;
    color: $log_text;
    border: 1px solid $zone_border;
    border-radius: 6px;
    font-family: 'Cascadia Mono', 'Consolas', monospace;
    font-size: 11px;
}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background: $input_bg;
    border: 1px solid $input_border;
    border-radius: 5px;
    padding: 5px 7px;
    color: $text;
    selection-background-color: $selection;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: $button_border;
}
QCheckBox {
    spacing: 8px;
}
QSlider::groove:horizontal {
    background: $slider_groove;
    height: 4px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: $accent;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QProgressBar {
    background: $progress_bg;
    border: 1px solid $progress_border;
    border-radius: 5px;
    height: 16px;
    text-align: center;
    color: $text;
}
QProgressBar::chunk {
    background: $accent;
    border-radius: 4px;
}
QScrollBar:vertical {
    background: $scroll_bg;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: $scroll_handle;
    border-radius: 5px;
}
QStatusBar {
    background: $status_bg;
    color: $status_text;
}
QSplitter::handle {
    background: $window;
}
"""
)

THEMES = {
    "Тёмная": _STYLE.substitute(_DARK),
    "Светлая": _STYLE.substitute(_LIGHT),
}
GLOBAL_STYLE = THEMES["Тёмная"]  # обратная совместимость
