# 01. Пайплайн

## Схема

```text
OpenCode (плагин photo-tools)   или   PyCharm / терминал   или   GUI (main.py)
  │
  ├── .venv\Scripts\python.exe            Poetry-окружение Python 3.14
  │     ├── src\photo_pipeline.py          CLI-адаптер (разбор аргументов)
  │     ├── src\ui\workers.py              QThread: прогресс и отмена
  │     └── src\core\                      основная логика
  │           ├── cutout.py                BiRefNet + pymatting, вырезка
  │           ├── backgrounds.py           Cloudflare / Google / Stability / HF / Pollinations
  │           ├── upscale.py               Real-ESRGAN ×4
  │           ├── compose.py               OpenCV, композит
  │           ├── progress.py              колбэки прогресса и check_cancel
  │           └── tasks.py                 файловые задачи для GUI
  ├── models\                              ONNX-модели внутри проекта
  └── data\                                все изображения
```

Плагин `photo-tools` — обёртка: запускает Python-скрипт и подставляет пути. `src\photo_pipeline.py` остался тонким CLI-адаптером, вся логика лежит в `src\core\`; пути запуска для плагина не изменились. Плагин берёт `.venv` и `src\photo_pipeline.py`, а если их нет — откатывается на старое окружение `%LOCALAPPDATA%\rembg-env`. GUI вызывает те же функции через `src\core\tasks.py` и `CoreWorker`, не запуская отдельный процесс.

## Проект и окружения

| Что | Путь |
|---|---|
| Корень проекта | `C:\My_projects\Photo` |
| Данные | `data\` (черновики — `data\bg\`, результаты — `data\results\`) |
| Код | `src\core\`, `src\photo_pipeline.py` (CLI), `src\contact_sheet.py`, `src\ui\` (GUI) |
| Модели | `models\faceparser.onnx`, `models\realesr-general-x4v3.onnx` |
| Poetry-окружение | `.venv\` (Python 3.14, интерпретатор PyCharm) |
| Метаданные Poetry | `pyproject.toml`, `poetry.lock` |
| Ключи | `%LOCALAPPDATA%\rembg-env\` (вне проекта) |
| Плагин | `C:\Users\bur_s\.config\opencode\plugins\photo-tools\index.ts` |
| Регистрация плагина | `C:\Users\bur_s\.config\opencode\opencode.json` |

Зависимости объявлены в `pyproject.toml` и установлены в `.venv`:

```text
rembg, onnxruntime, opencv-python-headless, pillow, pymatting, numpy, scipy
```

Отдельного «рабочего» окружения больше не требуется: `.venv` умеет всё. `%LOCALAPPDATA%\rembg-env` остаётся резервом и хранилищем ключей; плагин использует его только если проектные пути недоступны.

### Переменные окружения

| Переменная | Смысл |
|---|---|
| `PHOTO_PROJECT` | корень проекта для плагина (по умолчанию `C:/My_projects/Photo`) |
| `PHOTO_PYTHON` | интерпретатор для плагина |
| `PHOTO_PIPELINE` | путь к скрипту пайплайна |
| `PHOTO_MODELS` | каталог с ONNX-моделями |
| `PHOTO_RUNTIME_DIR` | где искать ключи (по умолчанию `%LOCALAPPDATA%\rembg-env`) |

## Инструменты плагина

| Инструмент | Что делает |
|---|---|
| `remove_background` | Вырезка объекта, portrait-режим по умолчанию |
| `composite_background` | Наложение вырезки на фон |
| `generate_background` | Генерация фона по промпту (по умолчанию в `data\bg\`) |
| `analyze_photo` | Технические параметры снимка |
| `recolor_hair` | Перекраска волос (в задаче не использовалась) |
| `upscale_image` | Апскейл ×4 |

## CLI

Все команды — из корня проекта, чтобы относительные пути (`data\bg\...`) работали одинаково в PowerShell и в PyCharm Terminal.

```powershell
$root = "C:\My_projects\Photo"
$data = "$root\data"
$py = "$root\.venv\Scripts\python.exe"
$pp = "$root\src\photo_pipeline.py"
Set-Location $root
```

### Вырезка

```powershell
& $py $pp cut "C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG" "$data\DSC00103-cut.png"
& $py $pp cut "in.jpg" "$data\out.png" --no-portrait
```

- По умолчанию включён портретный режим: тайловый BiRefNet + pymatting.
- Кадр покрывается целиком сеткой тайлов `tiling_plan()` из `src\core\cutout.py`: для стороны ≤ `2 × tile` — старые 2 тайла (с перекрытием, побайтово совпадает с результатом C), для больших кадров — шаг `tile // 2` (50 % перекрытия) и последний тайл впритык к краю, чтобы не оставалось непокрытых полос. Например, 2592×3456 даёт 4×6 = 24 тайла вместо прежних 4 с 53 % «дыр» посередине.
- Если отдельный тайл вышел почти сплошь непрозрачным (coverage > 0,9 — модель не нашла в нём объект), `_tile_with_context()` повторяет сегментацию с захватом `tile // 2` пикселей вокруг и вырезает исходную область. Так левая часть кадра 2048×1536, где модель видела только фон и возвращала сплошную маску, становится прозрачной. На утверждённом фото максимальный coverage тайла 0,61, поэтому повторов нет и результат остаётся побайтово тем же.
- Дополнительно кадр целиком прогоняется через ту же модель (`global_shape_alpha()` — ранний H-рецепт: растяжение альфы 8…247, жёсткие пороги, медиана 3). Перед pymatting `merge_global_shape()` добавляет к тайловой маске только те пиксели, где цельный кадр уверенно непрозрачен (>0,9), а тайлы почти прозрачны (<0,5); если таких пикселей меньше 0,1 % кадра, маска не меняется. Так у `DSCN1941.jpg` восстанавливается «провал» 566×532 px внизу фигуры и убираются пробелы по бокам, при этом цвет берётся из исходника (дыра: BGR `[110,64,64]` против `[127,77,72]` при старой заливке). На утверждённом фото доля таких пикселей 0,0158 % — ниже порога, поэтому вырезка остаётся побайтово той же (SHA-256 `682C29…396E`). Настоящие зазоры, которые на целом кадре тоже прозрачны, не заполняются.
- `cut_advisory(src)` возвращает предупреждения о большом или низкоконтрастном кадре; GUI показывает их всплывающим уведомлением в правом верхнем углу вкладки `Исходник` (5 с, закрывается крестиком) и дублирует в лог.
- Идёт 1–2 минуты на небольшом кадре и до ~7 минут на 24 тайлах — это норма, не зависание.
- Результат — RGBA PNG. Модель `birefnet-general` скачивается rembg в его кэш при первом запуске.

### Композит

```powershell
& $py $pp composite "$data\DSC00103-cut.png" "$data\bg\park-4x.jpg" "$data\final.jpg" `
  --shadow 0.22 --tone 1.06 --grain 4.5 --blur 2.0
```

| Параметр | По умолчанию | Смысл |
|---|---:|---|
| `--shadow` | 0.22 | Сила контактной тени под объектом |
| `--tone` | 1.06 | Подгонка яркости фона под объект |
| `--grain` | 4.5 | Зерно, чтобы фон не выглядел стерильным |
| `--blur` | 2.0 | Размытие фона |

Выходной путь обязателен третьим позиционным аргументом. Плагин подставляет его сам, в CLI указывать вручную.

### Генерация фона

```powershell
& $py $pp genbg "скалистый берег, чайки, облачно" "$data\bg\out.jpg" `
  --provider cloudflare `
  --size 2K
```

| Флаг | Значение |
|---|---|
| `--provider` | `auto`, `google`, `cloudflare`, `stability`, `huggingface`, `pollinations` |
| `--size` | `1K` (1024×768), `2K` (2048×1536), `4K` (4096×3072) — конечный размер файла |
| `--width`, `--height` | Влияют на соотношение сторон и кроп; у Pollinations ещё и на размер. Игнорируются при заданном `--size` |
| `--model` | Переопределение модели провайдера |
| `--no-upscale` | Не делать апскейл ×4 сразу после генерации (только без `--size`) |

Русский промпт переводится на английский автоматически (`src.core.prompt`, публичный endpoint Google Translate без ключа); упоминания разрешения («в 2К», «4k») удаляются. Если перевод недоступен, промпт уходит как есть.

По умолчанию `genbg` делает апскейл ×4, если модель `models\realesr-general-x4v3.onnx` на месте. Для черновиков быстрее `--no-upscale`. При заданном `--size` пресет важнее: результат сначала апскейлится ×4 (если провайдер отдал меньше), затем доводится до точного размера через `cv2.resize`.

### Апскейл

```powershell
& $py $pp upscale "$data\bg\in.jpg" "$data\bg\out-4x.jpg"
```

### Анализ

```powershell
& $py $pp analyze "C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG"
```

### Контактный лист

```powershell
& $py "$root\src\contact_sheet.py" "$data\bg\a.jpg" "$data\bg\b.jpg" --labels A B --out "$data\bg\compare.jpg"
```

Скрипт лежит в `src\` и использует Pillow из `.venv`.

## Порядок провайдеров

`--provider auto` перебирает:

```text
google → cloudflare → stability → huggingface → pollinations
```

Берётся первый, для которого есть ключ и который не упал. Для нужного провайдера лучше указывать `--provider` явно: иначе при появлении ключей выбор может измениться.

## Ключи

Ключи намеренно лежат **вне проекта** — их не нужно переносить и легко не закоммитить.

| Провайдер | Файл | Env |
|---|---|---|
| Google | `%LOCALAPPDATA%\rembg-env\google_api_key.txt` | `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `PHOTO_GOOGLE_KEY` |
| Cloudflare | `%LOCALAPPDATA%\rembg-env\cloudflare.json` | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `PHOTO_CLOUDFLARE_CREDS` |
| Stability | `%LOCALAPPDATA%\rembg-env\stability_api_key.txt` | `STABILITY_API_KEY`, `PHOTO_STABILITY_KEY` |
| Hugging Face | `%LOCALAPPDATA%\rembg-env\hf_token.txt` | `HF_TOKEN`, `HUGGINGFACE_TOKEN`, `PHOTO_HF_TOKEN` |

Формат `cloudflare.json`:

```json
{
  "account_id": "59cf71115d94a1596a9e865840194be6",
  "token": "cfat_..."
}
```

## Модели

| Файл | Размер | Для чего |
|---|---:|---|
| `models\faceparser.onnx` | 50,7 МБ | маска волос (`hair`) |
| `models\realesr-general-x4v3.onnx` | 4,6 МБ | апскейл ×4 |

Порядок поиска: `PHOTO_MODELS` → `<проект>\models` → `%LOCALAPPDATA%\rembg-env\models`. Модель `birefnet-general` для вырезки скачивается самим rembg при первом запуске в `%USERPROFILE%\.rembg\models` (около 930 МБ) и в `models\` не хранится.

## Особенности окружения

- **IPv6 зависает.** В `src\core\settings.py` стоит патч `socket.getaddrinfo`, который принудительно предпочитает IPv4 (применяется до импорта rembg). Сторонние клиенты и Node `fetch` этого патча не имеют — для разовых запросов использовать `curl.exe -4`.
- **Node/npm/bun не установлены.** TS-плагин не собирается; OpenCode загружает его сам. Если плагин не появился — смотреть `%USERPROFILE%\.local\share\opencode\log\opencode.log`.
- **Прав администратора нет.** `hosts` и системные установки недоступны.
- **PowerShell искажает кириллицу в консоли.** Файлы в UTF-8, это только отображение. Путь проекта ASCII; кириллица осталась только в пути исходника (`Изображения`).
