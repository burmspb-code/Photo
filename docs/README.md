# Документация: замена фона на фото

Проект обработки фотографий. Раньше это была рабочая папка с файлами, теперь — проект с кодом в `src\`, данными в `data\` и Poetry-окружением; разработка ведётся в PyCharm. Здесь описано, как устроен пайплайн, как повторить обработку и что уже сделано.

## Статус

- **Утверждённый результат:** `data/results/2026-11-17-park-c/final.jpg` (2026-11-17, вариант C). Карточка — [04-result-2026-11-17-park-c.md](04-result-2026-11-17-park-c.md), папка — [data/results/2026-11-17-park-c](../data/results/2026-11-17-park-c/README.md).
- **Исходник:** `C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG` (1632×1224).
- **Фон:** Cloudflare Workers AI, FLUX.1-schnell, затем апскейл ×4.
- Пользователь оценил результат положительно; правки не требуются.
- Перекраска волос в задачу не входила.
- **На будущее:** выбирать фоны без видимого источника света — иначе тени композита не совпадают с освещением лица (см. [03-backgrounds.md](03-backgrounds.md#правило-выбора-фона-по-свету)).

## Содержание

| Документ | О чём |
|---|---|
| [01-pipeline.md](01-pipeline.md) | Из чего состоит пайплайн: плагин, Python-скрипт, модели, ключи, команды |
| [02-workflow.md](02-workflow.md) | Пошаговый процесс: вырезка → фон → апскейл → композит → проверка → фиксация |
| [03-backgrounds.md](03-backgrounds.md) | Провайдеры генерации, цены и лимиты, настройка Cloudflare, промпты |
| [04-result-2026-11-17-park-c.md](04-result-2026-11-17-park-c.md) | Карточка утверждённого результата: параметры, команды, хеши |
| [05-troubleshooting.md](05-troubleshooting.md) | Типичные ошибки и что с ними делать |
| [06-development.md](06-development.md) | PyCharm, Poetry, `.venv` и резервное окружение `rembg-env` |

## Структура проекта

```text
C:\My_projects\Photo\
├── .venv\                  Poetry-окружение (Python 3.14), интерпретатор PyCharm
├── .idea\                  настройки PyCharm
├── data\                   все изображения
│   ├── DSC00103-cut.png            вырезка
│   ├── DSC00103-park-c.jpg         итог
│   ├── DSC00103-park-c-compare.jpg «до / после»
│   ├── bg\                         черновики фонов, реальные фото
│   └── results\                    утверждённые результаты
├── docs\                   эта документация
├── models\                 ONNX-модели (faceparser, realesr-general-x4v3)
├── src\                    код проекта
│   ├── __init__.py
│   ├── photo_pipeline.py           CLI-адаптер
│   ├── contact_sheet.py            контактные листы и сравнения
│   ├── ui\                         GUI на PyQt6
│   └── core\                       вырезка, фон, апскейл, композит
├── AGENTS.md               шпаргалка для агента
├── README.md               краткое описание проекта
├── pyproject.toml          метаданные Poetry
└── poetry.lock
```

Утверждённый результат лежит отдельно от черновиков:

```text
data/results/
└── 2026-11-17-park-c/
    ├── final.jpg              итог 1632×1224
    ├── compare.jpg            «до / после»
    ├── source.jpg             исходник
    ├── cutout.png             вырезка с прозрачным фоном
    ├── background-source.jpg  фон 1024×768 от Cloudflare
    ├── background-4x.jpg      фон после апскейла 4096×3072
    ├── manifest.json          метаданные и SHA-256
    └── README.md              краткая карточка
```

## Быстрый старт

```powershell
$root = "C:\My_projects\Photo"
$data = "$root\data"
$py = "$root\.venv\Scripts\python.exe"
$pp = "$root\src\photo_pipeline.py"
Set-Location $root

# 1. Вырезка (1–2 минуты)
& $py $pp cut "C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG" "$data\DSC00103-cut.png"

# 2. Черновик фона (Cloudflare, бесплатно)
& $py $pp genbg "photorealistic quiet park, soft overcast light, no people" "$data\bg\park-draft.jpg" --provider cloudflare --no-upscale

# 3. Апскейл ×4
& $py $pp upscale "$data\bg\park-draft.jpg" "$data\bg\park-draft-4x.jpg"

# 4. Композит
& $py $pp composite "$data\DSC00103-cut.png" "$data\bg\park-draft-4x.jpg" "$data\DSC00103-park.jpg" --blur 0.5
```

`$py` — `.venv` проекта: зависимости установлены Poetry. Если `.venv` недоступен, плагин и команды можно запускать python из `%LOCALAPPDATA%\rembg-env`. Подробнее — [06-development.md](06-development.md).

## Правила папки

- Изображения — только в `data\`; код — только в `src\`; документация — в `docs\`.
- Черновики и эксперименты — в `data\bg\`, имя по схеме `park-<вариант>.jpg`.
- Утверждённые результаты — только в `data/results/<дата>-<название>/`; содержимое не перезаписывать.
- `AGENTS.md` в корне — короткая шпаргалка для агента. Подробности — здесь.
- Путь проекта — ASCII. Кириллица осталась только в пути исходника (`C:\Users\bur_s\OneDrive\Изображения\...`), его всегда в кавычках.
