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
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.sizes import SIZE_ORDER

from .animated_combo import AnimatedComboBox
from .defaults import APP_DEFAULTS, CUT_MODELS, CUT_MODEL_HINTS, CUT_MODEL_PREVIEW, PROMPT_PLACEHOLDER
from .native_titlebar import apply_dark_titlebar, theme_is_dark
from .styles import THEME_WINDOW_COLORS

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
        self._dark_titlebar = theme_is_dark(parent)
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
        tabs.addTab(self._upscale_tab(), "Апскейл")
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        theme = "Тёмная" if self._dark_titlebar else "Светлая"
        apply_dark_titlebar(self, self._dark_titlebar, THEME_WINDOW_COLORS[theme])

    @property
    def prompt_text(self) -> str:
        """Введённый промпт (подсказка в текст не входит)."""
        return str(self.controls["bg/prompt"].toPlainText()).strip()

    def _add(self, form: QFormLayout, key: str, label: str, widget: QWidget, default) -> QWidget:
        form.addRow(label, widget)
        self.controls[key] = widget
        self.defaults[key] = APP_DEFAULTS.get(key, default)
        return widget

    @staticmethod
    def _combo(items, current=None) -> QComboBox:
        combo = AnimatedComboBox()
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
        form.addRow("Модель вырезки:", QLabel("на вкладке «Вырезка» или на панели задач"))
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
        sizes = {
            "birefnet-general": "~928 МБ",
            "birefnet-portrait": "~928 МБ",
            "isnet-general-use": "~170 МБ",
            "u2netp": "~4 МБ (превью)",
        }
        for name in CUT_MODELS:
            form.addRow(f"{name}:", QLabel(f"кэш rembg, {sizes.get(name, '—')}"))
        form.addRow("edsr-x2:", QLabel("models\\, 5,5 МБ (апскейл ×2)"))
        form.addRow("realesr-general-x4v3:", QLabel("models\\, 4,6 МБ (апскейл ×4)"))
        form.addRow("faceparser:", QLabel("models\\, 50,7 МБ (в задаче не используется)"))
        layout.addWidget(status)
        layout.addStretch()
        return page

    @staticmethod
    def _section(form: QFormLayout, title: str) -> None:
        """Заголовок группы внутри одной формы (занимает обе колонки)."""
        label = QLabel(title)
        label.setStyleSheet("font-weight: bold; padding-top: 8px;")
        form.addRow(label)

    def _cut_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # Без objectName Qt рисует вьюпорт/контент системным светлым цветом:
        # в тёмной теме светлый текст на нём нечитаем (та же ошибка, что была
        # в «О программе» и на панели параметров).
        scroll.viewport().setObjectName("settingsCutViewport")
        content = QWidget()
        content.setObjectName("settingsCutContent")
        form = QFormLayout(content)
        outer.addWidget(scroll)
        scroll.setWidget(content)

        self._section(form, "Модель и тайлы")
        model_combo = self._combo(CUT_MODELS)
        for index, name in enumerate(CUT_MODELS):
            model_combo.setItemData(index, CUT_MODEL_HINTS[name], Qt.ItemDataRole.ToolTipRole)
        model_combo.setToolTip(
            f"{CUT_MODEL_PREVIEW} — только для быстрого предпросмотра."
        )
        self._add(form, "cut/model", "Модель вырезки", model_combo, CUT_MODELS[0])
        self._add(form, "cut/portrait", "Портретный режим", QCheckBox(), True)
        self._add(form, "cut/tile", "Размер тайла", self._spin(256, 2048, 128), 1024)
        self._add(form, "cut/overlap", "Перекрытие тайлов", self._double(0.1, 0.9, 0.05, 2), 0.5).setToolTip(
            "Доля перекрытия соседних тайлов: больше — меньше швов, но дольше."
        )

        self._section(form, "Кромка")
        self._add(form, "cut/sigma", "Мягкость кромки (sigma)", self._double(0.2, 4.0, 0.1, 2), 1.4)
        self._add(form, "cut/head_ratio", "Доля головы", self._double(0.1, 0.8, 0.02, 2), 0.34)
        self._add(form, "cut/levels_lo", "Уровень альфы: низ", self._double(0.0, 0.5, 0.01, 2), 0.10)
        self._add(form, "cut/levels_hi", "Уровень альфы: верх", self._double(0.5, 1.0, 0.01, 2), 0.90)
        self._add(form, "cut/detail_gain", "Усиление деталей", self._double(0.0, 20.0, 0.5, 1), 7.0)
        self._add(form, "cut/detail_blur", "Размытие деталей", self._double(0.5, 10.0, 0.5, 1), 2.5)
        self._add(form, "cut/detail_weight", "Вес деталей", self._double(0.0, 1.0, 0.05, 2), 0.6)
        self._add(form, "cut/head_blur", "Размытие головы", self._double(1.0, 20.0, 1.0, 0), 6.0)
        self._add(form, "cut/head_weight", "Вес головы", self._double(0.0, 1.0, 0.05, 2), 0.6)
        self._add(form, "cut/matting", "Pymatting", QCheckBox(), True)

        self._section(form, "Цельный кадр (страховка)")
        self._add(form, "cut/global_shape", "Учитывать цельный кадр", QCheckBox(), True)
        widget = self._add(
            form, "cut/global_min_fraction", "Мин. доля добавления",
            self._double(0.0001, 0.02, 0.0001, 4), 0.001,
        )
        widget.setToolTip("Если цельный кадр предлагает добавить меньше этой доли пикселей, маска не меняется.")
        self._add(form, "cut/global_feather", "Растушёвка добавления", self._double(0.5, 10.0, 0.5, 1), 3.0)

        self._section(form, "Стабилизация альфы")
        self._add(form, "cut/stabilize", "Стабилизировать маску", QCheckBox(), True)
        widget = self._add(
            form, "cut/stabilize_min_mid", "Порог полупрозрачных",
            self._double(0.0, 0.3, 0.01, 2), 0.03,
        )
        widget.setToolTip("Ниже этой доли полупрозрачных пикселей маска не меняется вообще.")
        self._add(form, "cut/stabilize_noisy_mid", "Порог шума", self._double(0.0, 0.5, 0.01, 2), 0.10)
        self._add(form, "cut/stabilize_min_comps", "Порог числа компонент", self._spin(0, 500, 5), 50)
        self._add(form, "cut/stabilize_keep_ratio", "Доля крупных островков", self._double(0.001, 0.2, 0.005, 3), 0.02)
        self._add(form, "cut/stabilize_dilate", "Дилатация поддержки", self._spin(1, 31, 2), 7)
        self._add(form, "cut/stabilize_inner", "Внутренний радиус", self._spin(0, 20, 1), 3)

        self._section(form, "Обособленные элементы")
        self._add(form, "cut/isolated", "Удалять обособленные", QCheckBox(), True)
        widget = self._add(
            form, "cut/isolated_ratio", "Макс. доля от силуэта",
            self._double(0.005, 0.3, 0.005, 3), 0.15,
        )
        widget.setToolTip("Удаляются компоненты мельче этой доли от площади основного силуэта.")
        self._add(form, "cut/isolated_gap", "Мин. зазор, px", self._spin(4, 200, 4), 24).setToolTip(
            "При этом компоненты должны быть отделены от силуэта хотя бы на это расстояние."
        )
        self._add(form, "cut/isolated_halo", "Ореол удаления, px", self._spin(4, 80, 4), 32).setToolTip(
            "Насколько широко гасится альфа вокруг удалённой компоненты."
        )

        self._section(form, "Замкнутые пустоты")
        self._add(form, "cut/fill_holes", "Заливать верхние дыры", QCheckBox(), True).setToolTip(
            "Заливает мелкие замкнутые остатки фона в верхней части силуэта (сквозь волосы)."
        )
        self._add(form, "cut/hole_min_area", "Мин. площадь, px", self._spin(50, 2000, 50), 250).setToolTip(
            "Более мелкие дырочки относятся к деталям силуэта и не заливаются."
        )
        self._add(form, "cut/hole_max_area", "Макс. площадь, px", self._spin(200, 100000, 1000), 60000).setToolTip(
            "Более крупные замкнутые пустоты считаются частью формы и не заливаются."
        )
        self._add(
            form, "cut/hole_top_fraction", "Верхняя доля силуэта",
            self._double(0.1, 1.0, 0.05, 2), 0.5,
        ).setToolTip("Доля высоты силуэта сверху, в которой заливаются пустоты.")

        self._section(form, "Проработка волос")
        self._add(form, "cut/hair_refine", "Уплотнять кайму волос", QCheckBox(), True).setToolTip(
            "Поднимает альфу полупрозрачной каймы у головы, чтобы фон не просвечивал сквозь пряди."
        )
        self._add(
            form, "cut/hair_top_fraction", "Верхняя доля силуэта",
            self._double(0.1, 0.6, 0.05, 2), 0.30,
        ).setToolTip("Область уплотнения: доля высоты силуэта сверху.")
        self._add(
            form, "cut/hair_min_mid", "Мин. пикселей каймы",
            self._spin(1000, 200000, 1000), 25000,
        ).setToolTip(
            "Правило включается только при большом количестве полупрозрачных пикселей "
            "в области головы; чистые кадры не меняются."
        )
        self._add(form, "cut/hair_gain", "Коэффициент альфы", self._double(1.0, 4.0, 0.1, 2), 3.0).setToolTip(
            "Во сколько раз увеличивается альфа каймы: больше — плотнее волосы."
        )

        self._section(form, "Просветы между прядями")
        self._add(form, "cut/color_gaps", "Убирать по цвету фона", QCheckBox(), True).setToolTip(
            "Делает прозрачными пиксели, чей цвет близок к светло-голубому фону — просветы между прядями."
        )
        self._add(form, "cut/color_gap_lo", "Полное совпадение, d", self._double(0.0, 100.0, 5.0, 1), 45.0).setToolTip(
            "При цветовом расстоянии до фона меньше этого значения альфа становится нулевой."
        )
        self._add(form, "cut/color_gap_hi", "Не трогать, d", self._double(20.0, 255.0, 5.0, 1), 100.0).setToolTip(
            "При расстоянии больше этого значения альфа остаётся прежней; между ними — плавный переход."
        )
        self._add(
            form, "cut/color_gap_top_fraction", "Верхняя доля силуэта",
            self._double(0.1, 1.0, 0.05, 2), 0.35,
        ).setToolTip("Область очистки: доля высоты силуэта сверху.")
        self._add(
            form, "cut/color_gap_min_blue", "Мин. синий минус красный",
            self._double(0.0, 100.0, 5.0, 1), 25.0,
        ).setToolTip(
            "Правило включается, только если фон светло-голубой: синий канал фона "
            "должен превосходить красный хотя бы на это значение. Другие кадры не меняются."
        )

        self._section(form, "Выход")
        self._add(form, "cut/format", "Формат выхода", self._combo(["PNG (RGBA)", "JPEG"]), "PNG (RGBA)")
        return page

    def _background_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        prompt = QPlainTextEdit()
        prompt.setPlaceholderText(PROMPT_PLACEHOLDER)
        prompt.setFixedHeight(80)
        # Без Fixed по вертикали QFormLayout растягивает все строки под
        # Expanding-поле, и параметры оказываются разнесены большими пустотами.
        prompt.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._add(form, "bg/prompt", "Промпт", prompt, "")
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

    def _upscale_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        combo = AnimatedComboBox()
        combo.addItem("×2 — EDSR (быстро, мелкие детали)", 2)
        combo.addItem("×4 — Real-ESRGAN (утверждённый стиль)", 4)
        self._add(form, "upscale/factor", "Кратность", combo, APP_DEFAULTS["upscale/factor"])
        note = QLabel(
            "×2 — EDSR (5,5 МБ): быстрее и лучше сохраняет мелкие детали; "
            "рекомендуемый режим.\n"
            "×4 — realesr-general-x4v3 (4,6 МБ): стиль утверждённого результата.\n"
            "На этом кадре ×2 увеличивает стороны исходника вдвое, ×4 — вчетверо.\n"
            "Внутренняя обработка фонов использует ×4 независимо от этой настройки."
        )
        note.setWordWrap(True)
        form.addRow(note)
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
        hints = self._add(
            form, "ui/hints", "Подсказки в инфоокне", QCheckBox(),
            APP_DEFAULTS["ui/hints"],
        )
        hints.setToolTip("Советы о следующем шаге в нижнем окне сообщений ([HINT])")
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
                value = self.settings.value(key, default)
                # Данные в комбо бывают двух видов: число (кратность апскейла)
                # или строка-подсказка (модели вырезки). Раньше проверяли
                # ``itemData(0) is None``, и подсказки ломали восстановление:
                # int('birefnet-portrait') падал, выбор сбрасывался на дефолт.
                if isinstance(widget.itemData(0), int):
                    try:
                        index = widget.findData(int(value))
                    except (TypeError, ValueError):
                        index = -1
                else:
                    index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(self.settings.value(key, default)))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(self.settings.value(key, default)))
            elif isinstance(widget, QPlainTextEdit):
                # Промпт не сохраняется между запусками — в поле всегда подсказка.
                if key != "bg/prompt":
                    widget.setPlainText(str(self.settings.value(key, default)))
            elif isinstance(widget, QLabel):
                widget.setText(str(self.settings.value(key, default)))
            else:
                widget.setText(str(self.settings.value(key, default)))
        self._update_provider_info()

    def _save(self) -> None:
        for key, widget in self.controls.items():
            if key == "bg/prompt":
                continue  # одноразовый ввод, не настройка
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QComboBox):
                # Combo с данными (кратность апскейла) сохраняет число, а не подпись.
                data = widget.currentData()
                value = data if data is not None else widget.currentText()
            elif isinstance(widget, QLabel):
                value = widget.text()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                value = widget.value()
            elif isinstance(widget, QPlainTextEdit):
                value = widget.toPlainText()
            else:
                value = widget.text()
            self.settings.setValue(key, value)
        self.settings.remove("bg/prompt")  # удалить текст прошлой генерации
        self.settings.sync()
        self.accept()

    def _reset(self) -> None:
        self.settings.clear()
        self._load()
