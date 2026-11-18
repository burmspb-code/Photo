"""Диалог «О программе»: простыми словами о задаче, шагах и инструментах.

Текст рассчитан на пользователя без опыта в обработке фото: сначала объясняется,
какую проблему решает приложение, затем — что нужно нажать, и лишь потом
перечисляются используемые модели с кратким пояснением «что это даёт».
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .native_titlebar import apply_dark_titlebar, theme_is_dark

APP_TITLE = "Photo — замена фона на фотографии"

PURPOSE = (
    "Представьте: снимок удачный, а фон — нет: тесная комната, стройка или просто "
    "скучная стена. Это приложение помогает оставить на фото только человека или "
    "предмет и поставить его в другое место — в парк, на берег моря, в светлый "
    "офис. Новый фон можно придумать самому, просто описав его словами, или взять "
    "готовую картинку."
)

STEPS = (
    "<ol>"
    "<li>Откройте фото: меню <b>Файл</b> → <b>Открыть исходное фото</b>.</li>"
    "<li>Нажмите <b>Вырезать объект</b> — программа сама отделит объект от старого фона.</li>"
    "<li>Опишите нужный фон и нажмите <b>Сгенерировать фон</b> или откройте свою "
    "картинку кнопкой <b>Выбрать фон</b>.</li>"
    "<li>Нажмите <b>Собрать композит</b> и сохраните результат.</li>"
    "</ol>"
)

TOOLS = (
    "<ul>"
    "<li><b>Вырезка</b> — модели BiRefNet и ISNet (библиотека rembg). Они работают "
    "прямо на вашем компьютере. Для аккуратных краёв, например волос, используется "
    "pymatting.</li>"
    "<li><b>Новый фон</b> — облачный искусственный интеллект: по умолчанию "
    "FLUX 1 schnell (Cloudflare), также доступны Google, Stability AI, Hugging Face "
    "и Pollinations. Писать можно по-русски — текст автоматически переводится на "
    "английский. Размер файла выбирается пресетом, но детали зависят от модели — "
    "подробнее ниже.</li>"
    "<li><b>Увеличение</b> — если фон мельче снимка, его можно увеличить: по "
    "умолчанию модель EDSR в 2 раза, а в настройках доступен Real-ESRGAN в 4 раза. "
    "Размер результата при этом остаётся как у исходного фото.</li>"
    "<li><b>Сборка</b> — OpenCV настраивает размытие фона, контактную тень, яркость "
    "и лёгкое зерно, чтобы объект выглядел естественно.</li>"
    "<li><b>Удобство</b> — интерфейс на PyQt6: долгие операции идут в фоне, есть "
    "прогресс и кнопка <b>Стоп</b>, чтобы прервать задачу.</li>"
    "</ul>"
)

PRIVACY = (
    "При вырезке ваше фото <b>не отправляется в интернет</b> — всё считается на "
    "вашем компьютере. Когда вы просите придумать фон, наружу уходит только текст "
    "запроса, сам снимок туда не передаётся."
)

RESOLUTION = (
    "В настройках можно выбрать размер фона: <b>1K</b> (1024×768), <b>2K</b> "
    "(2048×1536) или <b>4K</b> (4096×3072). Это размер итогового файла, но важно "
    "понимать: детали зависят от модели, которая рисует фон. Например, Cloudflare "
    "FLUX 1 schnell создаёт картинку 1024×1024, и после обрезки под формат фото "
    "остаётся 1024×768. Если вы выбрали 2K или 4K, приложение увеличивает её в 4 "
    "раза и подгоняет под нужный размер. Поэтому большой файл не всегда значит "
    "больше реальных деталей — качество ограничено возможностями подключённой "
    "модели. Если важна высокая детализация, выберите более сильную модель или "
    "откройте готовое фото с высоким разрешением."
)

MARKET = (
    "<p>Похожие сервисы: remove.bg, Adobe Express, Canva, Photoroom, Pixelcut и "
    "Photoshop. Большинство из них работают онлайн и предлагают бесплатные "
    "возможности с лимитами, водяными знаками или подпиской. По данным обзоров, "
    "remove.bg закрывает отдельный сайт и API 1 декабря 2026 года.</p>"
    "<p><b>Чем это приложение отличается:</b></p>"
    "<ul>"
    "<li>Все шаги в одном окне — не нужно переключаться между сайтами и вручную "
    "переносить файлы.</li>"
    "<li>Вырезка и сборка выполняются на вашем компьютере: снимок не уезжает на "
    "чужой сервер.</li>"
    "<li>У самого приложения нет подписки и водяных знаков (внешние сервисы "
    "генерации фона могут иметь свои лимиты).</li>"
    "<li>Русский запрос понимается без перевода вручную.</li>"
    "<li>Настройки реализма — тень, свет, зерно — и проверенные значения по "
    "умолчанию помогают получить естественный результат.</li>"
    "</ul>"
)


def _section(title: str, body: str, name: str) -> QLabel:
    label = QLabel(f"<h3>{title}</h3>{body}")
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class AboutDialog(QDialog):
    """Окно с описанием приложения, шагами и использованными инструментами."""

    def __init__(self, parent: QWidget | None = None, dark: bool | None = None) -> None:
        super().__init__(parent)
        self._dark_titlebar = theme_is_dark(parent) if dark is None else dark
        self.setWindowTitle("О программе")
        self.setMinimumSize(560, 520)

        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Без собственного objectName вьюпорт рисуется системным светлым цветом,
        # и в тёмной теме светлый текст становится нечитаемым.
        scroll.viewport().setObjectName("aboutViewport")
        content = QWidget()
        content.setObjectName("aboutContent")
        inner = QVBoxLayout(content)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(12)

        title = QLabel(f"<h2>{APP_TITLE}</h2>")
        title.setObjectName("aboutTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.addWidget(title)
        inner.addWidget(_section("Для чего это нужно", PURPOSE, "aboutPurpose"))
        inner.addWidget(_section("Как пользоваться", STEPS, "aboutSteps"))
        inner.addWidget(_section("Какие инструменты работают внутри", TOOLS, "aboutTools"))
        inner.addWidget(_section("О размере фона", RESOLUTION, "aboutResolution"))
        inner.addWidget(_section("О приватности", PRIVACY, "aboutPrivacy"))
        inner.addWidget(_section("Похожие продукты и преимущества", MARKET, "aboutMarket"))
        scroll.setWidget(content)
        layout.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # HWND уже создан — красим системную шапку под выбранную тему.
        apply_dark_titlebar(self, self._dark_titlebar)
