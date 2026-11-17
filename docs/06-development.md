# 06. Разработка: PyCharm, Poetry, окружения

Проект живёт в `C:\My_projects\Photo`, открывается в PyCharm и управляется Poetry. Код пайплайна теперь внутри проекта, зависимости объявлены и установлены в `.venv`.

## Структура

```text
C:\My_projects\Photo\
├── .venv\                  Poetry-окружение, Python 3.14
├── .idea\                  настройки PyCharm
├── data\                   изображения: bg\, results\
├── docs\                   документация
├── models\                 ONNX-модели (faceparser, realesr-general-x4v3)
├── src\
│   ├── __init__.py
│   ├── photo_pipeline.py   вырезка, фон, апскейл, композит
│   └── contact_sheet.py    контактные листы
├── AGENTS.md
├── README.md
├── pyproject.toml
└── poetry.lock
```

## Что изменилось при переезде

| Было | Стало |
|---|---|
| `Фото\*.jpg`, `Фото\bg\`, `Фото\results\` | `data\*.jpg`, `data\bg\`, `data\results\` |
| `Фото\scripts\contact_sheet.py` | `src\contact_sheet.py` |
| `rembg-env\photo_pipeline.py` | `src\photo_pipeline.py` |
| Модели в `rembg-env\models` | `models\` в проекте (плюс fallback) |
| Голый Python в `rembg-env` | `.venv` с зависимостями из `pyproject.toml` |
| Плагин с путями в `rembg-env` | Плагин с проектными путями и fallback |

## Окружения

| | `.venv` | `%LOCALAPPDATA%\rembg-env` |
|---|---|---|
| Назначение | основное: код, пайплайн, тесты | резерв и хранилище ключей |
| Python | 3.14 | 3.14 |
| Пакеты | rembg, onnxruntime, opencv-python-headless, pillow, pymatting, numpy, scipy | те же плюс ручные установки |
| Метаданные | Poetry (`pyproject.toml`, `poetry.lock`) | без Poetry |
| Когда использовать | всегда, если доступен | если `.venv` сломан/удалён |

Плагин `photo-tools` сам выбирает `.venv` и `src\photo_pipeline.py`. Если их нет — откатывается на `rembg-env`, поэтому удаление `.venv` не ломает инструменты насовсем.

## Зависимости

`pyproject.toml`:

```toml
[project]
name = "photo"
version = "0.1.0"
requires-python = "^3.14"
dependencies = [
    "rembg (>=2.0.87,<3.0.0)",
    "onnxruntime (>=1.32.0,<2.0.0)",
    "opencv-python-headless (>=5.0.0.93,<6.0.0.0)",
    "pillow (>=13.0.0,<14.0.0)",
    "pymatting (>=1.1.16,<2.0.0)",
    "numpy (>=2.5.5,<3.0.0)",
    "scipy (>=1.18.1,<2.0.0)",
]
```

Установка на новой машине:

```powershell
Set-Location "C:\My_projects\Photo"
poetry install
```

`poetry.lock` фиксирует 31 пакет, включая транзитивные (`scikit-image`, `numba`, `onnxruntime`, `requests` и т. д.). `readme = "README.md"` — файл в корне обязателен, иначе сборка Poetry падает (он уже есть).

## PyCharm

1. **File → Open** → `C:\My_projects\Photo`.
2. **Settings → Project → Python Interpreter** → `.venv\Scripts\python.exe` (Python 3.14). Уже прописан в `.idea\misc.xml`.
3. Терминал PyCharm открывается в корне проекта — команды из [02-workflow.md](02-workflow.md) работают без `cd`.
4. Run Configuration для пайплайна:
   - script: `src\photo_pipeline.py`;
   - parameters: `composite data\DSC00103-cut.png data\bg\park-flux-c-4x.jpg data\test.jpg --blur 0.5`;
   - working directory: `C:\My_projects\Photo`.
5. `.idea\` и `.venv\` не предназначены для версионирования. Git в проекте пока не инициализирован; при инициализации добавить `.venv/`, `.idea/`, `__pycache__/` в `.gitignore`, а `models\` — в Git LFS или внешнее хранилище.

## Модели

| Файл | Размер | Для чего |
|---|---:|---|
| `models\faceparser.onnx` | 50,7 МБ | маска волос (`hair`) |
| `models\realesr-general-x4v3.onnx` | 4,6 МБ | апскейл ×4 |

Порядок поиска: `PHOTO_MODELS` → `<проект>\models` → `%LOCALAPPDATA%\rembg-env\models`. Модель `birefnet-general` для вырезки скачивается самим rembg при первом запуске в `%USERPROFILE%\.rembg\models` (около 930 МБ).

## Переменные окружения пайплайна

| Переменная | Смысл |
|---|---|
| `PHOTO_PROJECT` | корень проекта для плагина |
| `PHOTO_PYTHON` | интерпретатор |
| `PHOTO_PIPELINE` | путь к `photo_pipeline.py` |
| `PHOTO_MODELS` | каталог моделей |
| `PHOTO_RUNTIME_DIR` | где искать ключи (по умолчанию `rembg-env`) |
| `PHOTO_GOOGLE_KEY`, `PHOTO_GOOGLE_KEY_FILE` | Google-ключ |
| `PHOTO_CLOUDFLARE_CREDS` | `cloudflare.json` |
| `PHOTO_HF_TOKEN`, `PHOTO_STABILITY_KEY` | остальные ключи |

## Что сделано и что дальше

Сделано:

- [x] `photo_pipeline.py` перенесён в `src\`.
- [x] Зависимости объявлены в `pyproject.toml` и установлены в `.venv`.
- [x] Модели скопированы в `models\`, добавлен fallback на `rembg-env`.
- [x] Плагин переключён на `.venv` и `src\photo_pipeline.py` с откатом.
- [x] Проверены `analyze`, `composite`, `contact_sheet` на новом окружении.

Дальше по желанию:

1. Разбить `photo_pipeline.py` на модули (`cutout`, `generators`, `compose`) и добавить `__main__.py`.
2. Тесты: кроп аспекта, композит, контактный лист, парсинг CLI.
3. Git + `.gitignore` + LFS для `models\` или вынести модели в `%LOCALAPPDATA%`.
4. Закрепить Python-версию и добавить `ruff`/`pytest` в dev-зависимости.
