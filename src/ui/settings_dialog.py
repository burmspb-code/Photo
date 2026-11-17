"""Диалог настроек: параметры моделей и пользовательские параметры.

Значения читаются и пишутся в QSettings и используются ядром через
``MainWindow.current_params()``. Предустановки берутся из ``ui.defaults`` —
одного источника проверенных значений. Ключи API в диалоге не показываются.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.sizes import SIZE_ORDER

from .defaults import APP_DEFAULTS

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
PROVIDERS = ("cloudflare", "google", "stability", "huggingface", "pollinations")

# Модели по умолчанию совпадают с вызовами в src.core.backgrounds.genbg().
PROVIDER_INFO = {
    "cloudflare": ("Cloudflare", "@cf/black-forest-labs/flux-1-schnell"),
    "google": ("Google", "gemini-nano-banana-2.1"),
    "stability": ("Stability AI", "sd3.5-large"),
    "huggingface": ("Hugging Face", "black-forest-labs/FLUX.1-schnell"),
    "pollinations": ("Pollinations", "image.pollinations.ai"),
}


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("Photo", "Photo")
        self.controls: dict[str, QWidget] = {}
        self.defaults: dict[str, object] = {}
        self.generate_requested = False  # кнопка «Сгенерировать» в диалоге

        self.setWindowTitle("Настройки")
        self.resize(760, 600)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._models_tab(), "Модели")
        tabs.addTab(self._cut_tab(), "Вырезка")
        tabs.addTab(self._background_tab(), "Фон")
        tabs.addTab(self._compose_tab(), "Композит")
        tabs.addTab(self._paths_tab(), "Пути")
        tabs.addTab(self._common_tab(), "Общие")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Подключаем после создания всех вкладок: слот обновляет обе метки.
        self.controls["bg/provider_api"].currentTextChanged.connect(self._update_provider_info)
        self._load()

    def _add(self, form: QFormLayout, key: str, label: str, widget: QWidget, default) -> QWidget:
        form.addRow(label, widget)
        self.controls[key] = widget
        self.defaults[key] = APP_DEFAULTS.get(key, default)
        return widget

    @staticmethod
    def _combo(items, current=None) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        if current is not None:
            combo.setCurrentText(current)
        return combo

    @staticmethod
    def _spin(lo: int, hi: int, step: int = 1) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        return spin

    @staticmethod
    def _double(lo: float, hi: float, step: float, decimals: int = 2) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        return spin

    def _update_provider_info(self) -> None:
        """Показать текущего провайдера, его модель и наличие ключа."""
        provider = str(self.controls["bg/provider_api"].currentText())
        title, model = PROVIDER_INFO.get(provider, (provider, "—"))
        # Тяжёлый модуль ядра импортируем только при открытии настроек.
        from src.core.backgrounds import cf_creds, google_key, hf_token, stability_key

        checks = {
            "cloudflare": lambda: all(cf_creds()),
            "google": lambda: bool(google_key()),
            "stability": lambda: bool(stability_key()),
            "huggingface": lambda: bool(hf_token()),
        }
        if provider in checks:
            status = "ключ найден" if checks[provider]() else "ключ не найден"
        else:
            status = "ключ не нужен"
        self.provider_info.setText(f"Сейчас: {title} · {model}\n{status}")
        self.background_model.setText(f"{title} · {model}")

    def _generate(self) -> None:
        """Сохранить настройки и закрыться: MainWindow запустит генерацию."""
        self.generate_requested = True
        self._save()

    def _models_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        cut = QGroupBox("Локальные модели")
        form = QFormLayout(cut)
        self._add(form, "cut/model", "Модель вырезки", self._combo(CUT_MODELS), CUT_MODELS[0])
        self._add(
            form, "models/upscale", "Модель апскейла",
            self._combo(["realesr-general-x4v3", "—"]), "realesr-general-x4v3",
        )
        layout.addWidget(cut)

        cloud = QGroupBox("Фон (провайдер API)")
        form = QFormLayout(cloud)
        self._add(
            form, "bg/provider_api", "Провайдер по умолчанию", self._combo(PROVIDERS), "cloudflare"
        )
        self.provider_info = QLabel()
        self.provider_info.setObjectName("providerInfo")
        self.provider_info.setWordWrap(True)
        form.addRow("Подключено:", self.provider_info)
        info = QLabel(
            "Ключи хранятся вне репозитория в %LOCALAPPDATA%\\rembg-env\\ — здесь показывается "
            "только их наличие. Модель задаётся в коде провайдера (или env PHOTO_GOOGLE_MODEL)."
        )
        info.setWordWrap(True)
        form.addRow(info)
        layout.addWidget(cloud)

        status = QGroupBox("Статус")
        form = QFormLayout(status)
        form.addRow("birefnet-general:", QLabel("кэш rembg, ~928 МБ"))
        form.addRow("realesr-general-x4v3:", QLabel("models\\, 4,6 МБ"))
        form.addRow("faceparser:", QLabel("models\\, 50,7 МБ (в задаче не используется)"))
        layout.addWidget(status)
        layout.addStretch()
        return page

    def _cut_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._add(form, "cut/portrait", "Портретный режим", QCheckBox(), True)
        self._add(form, "cut/tile", "Размер тайла", self._spin(256, 2048, 128), 1024)
        self._add(form, "cut/sigma", "Мягкость кромки (sigma)", self._double(0.2, 4.0, 0.1, 2), 1.4)
        self._add(form, "cut/head_ratio", "Доля головы", self._double(0.1, 0.8, 0.02, 2), 0.34)
        self._add(form, "cut/matting", "Pymatting", QCheckBox(), True)
        self._add(form, "cut/format", "Формат выхода", self._combo(["PNG (RGBA)", "JPEG"]), "PNG (RGBA)")
        return page

    def _background_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        prompt = QPlainTextEdit()
        prompt.setFixedHeight(80)
        self._add(
            form, "bg/prompt", "Промпт", prompt,
            "realistic photo, no people, no text, soft overcast light",
        )
        generate = QPushButton("Сгенерировать фон")
        generate.setObjectName("settingsGenerate")
        generate.setToolTip("Применить настройки и сразу сгенерировать фон")
        generate.clicked.connect(self._generate)
        form.addRow("", generate)
        self.background_model = QLabel()
        self.background_model.setObjectName("backgroundModel")
        # QFormLayout растягивает QLabel по высоте строки и центрирует текст —
        # из-за этого значение «Модели» уезжало вниз. Фиксируем высоту и верхнее
        # выравнивание, чтобы подпись и значение были на одной строке.
        self.background_model.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.background_model.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.addRow("Модель:", self.background_model)
        self._add(form, "bg/drafts", "Число черновиков", self._spin(1, 12), 3)
        self._add(form, "bg/aspect", "Соотношение сторон", self._combo(["4:3", "3:2", "1:1", "16:9"]), "4:3")
        self._add(form, "bg/seed", "Seed", self._spin(0, 999999), 7)
        self._add(form, "bg/size", "Размер фона", self._combo(SIZE_ORDER), "2K")
        return page

    def _compose_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._add(form, "compose/blur", "Размытие фона", self._double(0.0, 4.0, 0.1, 2), 0.5)
        self._add(form, "compose/shadow", "Контактная тень", self._double(0.0, 0.5, 0.01, 2), 0.22)
        self._add(form, "compose/tone", "Подгонка яркости", self._double(0.8, 1.3, 0.01, 2), 1.06)
        self._add(form, "compose/grain", "Зерно", self._double(0.0, 12.0, 0.5, 1), 4.5)
        self._add(form, "compose/seed", "Seed", self._spin(0, 999999), 7)
        return page

    def _paths_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._add(form, "paths/data", "Каталог данных", QLabel("data\\"), "data\\")
        self._add(form, "paths/models", "Каталог моделей", QLabel("models\\"), "models\\")
        self._add(
            form, "paths/cache", "Кэш вырезки",
            QLabel("%USERPROFILE%\\.rembg\\models"), "%USERPROFILE%\\.rembg\\models",
        )
        note = QLabel(
            "Изменять пути пока нельзя — значения используются только для отображения.\n"
            "Реальные пути берутся из переменных окружения PHOTO_* (см. docs/01-pipeline.md)."
        )
        note.setWordWrap(True)
        form.addRow(note)
        return page

    def _common_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._add(form, "ui/language", "Язык", self._combo(["Русский"]), "Русский")
        self._add(form, "ui/log_level", "Уровень лога", self._combo(["INFO", "WARN", "ERROR", "DEBUG"]), "INFO")
        reset = QPushButton("Сбросить настройки")
        reset.clicked.connect(self._reset)
        form.addRow(reset)
        return page

    def _load(self) -> None:
        for key, widget in self.controls.items():
            default = self.defaults[key]
            if isinstance(widget, QCheckBox):
                widget.setChecked(self.settings.value(key, default, type=bool))
            elif isinstance(widget, QComboBox):
                index = widget.findText(str(self.settings.value(key, default)))
                if index >= 0:
                    widget.setCurrentIndex(index)
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(self.settings.value(key, default)))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(self.settings.value(key, default)))
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(str(self.settings.value(key, default)))
            elif isinstance(widget, QLabel):
                widget.setText(str(self.settings.value(key, default)))
            else:
                widget.setText(str(self.settings.value(key, default)))
        self._update_provider_info()

    def _save(self) -> None:
        for key, widget in self.controls.items():
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, (QComboBox, QLabel)):
                value = widget.currentText() if isinstance(widget, QComboBox) else widget.text()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                value = widget.value()
            elif isinstance(widget, QPlainTextEdit):
                value = widget.toPlainText()
            else:
                value = widget.text()
            self.settings.setValue(key, value)
        self.settings.sync()
        self.accept()

    def _reset(self) -> None:
        self.settings.clear()
        self._load()
