# AGENTS.md

## Проект
- Корень: `C:\My_projects\Photo` (ASCII-путь, git нет). PyCharm + Poetry, Python 3.14 в `.venv`.
- Исходник: `C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG` (1632×1224). Вырезка: `data\DSC00103-cut.png` (RGBA).
- Задача: заменить фон на реалистичный парк; реализм и детализацию оценивает пользователь. Перекраска волос вне задачи.
- **Документация:** `docs\` — начни с [docs/README.md](docs/README.md). Пайплайн — [01-pipeline.md](docs/01-pipeline.md), процесс — [02-workflow.md](docs/02-workflow.md), фоны — [03-backgrounds.md](docs/03-backgrounds.md), окружения — [06-development.md](docs/06-development.md), ошибки — [05-troubleshooting.md](docs/05-troubleshooting.md).
- **Утверждённый результат:** `data\results\2026-11-17-park-c\` (вариант C, 2026-11-17), карточка — [04-result-2026-11-17-park-c.md](docs/04-result-2026-11-17-park-c.md).
- Черновики — в `data\bg\`, утверждённое — только в `data\results\<дата>-<название>\` (не перезаписывать).
- `data\bg\real_*.jpg` — реальные фото парков (4–6 тыс. px), резерв при недоступной генерации.

## Структура
```text
Photo\
├── data\        изображения: bg\ (черновики), results\ (утверждённое)
├── docs\        документация
├── models\      ONNX-модели: faceparser, edsr-x2, realesr-general-x4v3
├── src\         код: photo_pipeline.py, contact_sheet.py
├── .venv\       Poetry-окружение (Python 3.14) с зависимостями пайплайна
├── pyproject.toml, poetry.lock
└── AGENTS.md, README.md
```

## Пайплайн
- Глобальный плагин `photo-tools` (`~/.config/opencode/plugins/photo-tools/index.ts`, регистрация в `~/.config/opencode/opencode.json`) даёт namespace `photo`.
- По умолчанию плагин берёт `.venv\Scripts\python.exe` и `src\photo_pipeline.py`; если их нет — откатывается на `%LOCALAPPDATA%\rembg-env`.
- Переопределение: env `PHOTO_PROJECT`, `PHOTO_PYTHON`, `PHOTO_PIPELINE`, `PHOTO_MODELS`, `PHOTO_RUNTIME_DIR`.
- Модели ищутся: `PHOTO_MODELS` → `<проект>\models` → `rembg-env\models`.
- Команды — из корня проекта:

```powershell
$root = "C:\My_projects\Photo"
$data = "$root\data"
$py = "$root\.venv\Scripts\python.exe"
$pp = "$root\src\photo_pipeline.py"
Set-Location $root
& $py $pp cut "C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG" "$data\DSC00103-cut.png"
& $py $pp composite "$data\DSC00103-cut.png" "$data\bg\bg.jpg" "$data\final.jpg" --blur 0.5
& $py $pp genbg "prompt" "$data\bg\out.jpg" --provider cloudflare --no-upscale
& $py $pp upscale "$data\bg\out.jpg" "$data\bg\out-2x.jpg" --factor 2   # ×4: --factor 4
```

- `cut` идёт 1–2 минуты (тайловый BiRefNet + pymatting) — это норма, не зависание.
- `composite` требует выходной путь третьим позиционным аргументом; плагин подставляет его сам.
- Для апскейленного фона ставь `--blur 0.5–0.8`, иначе композит выглядит мыльным.
- Контактные листы и сравнения «до/после»: `src\contact_sheet.py` (`--labels A B C --out data\bg\compare.jpg`), запускать `.venv` python.

## Правило фона
- Для будущих фонов предпочтительнее кадры **без видимого источника света**: мягкий рассеянный свет, облачность, тень. Иначе тени в композите не совпадают с освещением лица.
- Промпт обязательно содержит `realistic photo, no people, no text`.

## Подводные камни
- `--width/--height` влияют только на Pollinations; Google, Cloudflare, Stability и HF сами выбирают формат, `_crop_aspect` затем кропает до нужного (Stability просит 3:2 и кропает до 4:3).
- Порядок `provider=auto` в коде: `google → cloudflare → stability → huggingface → pollinations`. Для нужного провайдера выбирать `--provider` явно.
- Google Imagen полностью отключён. Актуальный путь — Interactions API (`/v1beta/interactions`) с моделями `gemini-nano-banana-2.1` (по умолчанию), `gemini-3.1-flash-lite-image`, `gemini-3.1-flash-image`, `gemini-3-pro-image`. У Gemini image-моделей **нет бесплатного тарифа**: ~$0.0336 за 1K-картинку, нужен включённый биллинг.
- VPN снял региональные блокировки. Блокер — ключи/биллинг: ключей Google и Stability нет, HF отдаёт 402. Рабочий путь — Cloudflare.
- Практический приоритет генерации: Cloudflare FLUX.1-schnell (бесплатно, 10 000 neurons/день) → Google Nano Banana (платно, ~$0.034/кадр, лучшее качество, когда появится биллинг) → Stability SD3.5 (25 кредитов) → Pollinations.
- Cloudflare отдаёт 1024×1024, кроп до 4:3 → 1024×768; для итога нужен апскейл ×4.
- `/user/tokens/verify` для токена Cloudflare отдаёт `Invalid API Token`, хотя `/accounts` и генерация работают — не считать токен недействительным по verify.
- HF Inference бесплатно не работает: любой живой провайдер (fal-ai, replicate, hf-inference) отдаёт `402 Purchase pre-paid credits`. Старый `hf-inference` + FLUX.1-schnell даёт `410 model is deprecated`.
- IPv6 в этой сети зависает. Пайплайн принудительно использует IPv4; для разовых запросов — `curl.exe -4`. Node `fetch` и Python HTTP без патча будут таймаутиться.
- Прав администратора нет: `hosts` и системные установки недоступны.
- Node/npm/bun не установлены. TS-плагин не собирать; OpenCode загружает его сам. Если плагин не появился — смотреть `%USERPROFILE%\.local\share\opencode\log\opencode.log`.
- PowerShell портит кириллицу в консоли; файлы в UTF-8. Кириллица осталась только в пути исходника (`Изображения`), путь проекта — ASCII.
- `pyproject.toml` ссылается на `README.md` в корне — файл должен существовать, иначе ломается сборка Poetry.
- `models\` — 55 МБ ONNX-файлов внутри проекта; не коммитить в git без LFS.

## Ключи и модели
- Ключи лежат вне проекта, в `%LOCALAPPDATA%\rembg-env\` (или env `PHOTO_RUNTIME_DIR`): `hf_token.txt`, `cloudflare.json`; нет `stability_api_key.txt`, `google_api_key.txt`.
- Переопределение путей к ключам: `PHOTO_GOOGLE_KEY`, `PHOTO_GOOGLE_KEY_FILE`, `PHOTO_CLOUDFLARE_CREDS`, `PHOTO_HF_TOKEN`, `PHOTO_STABILITY_KEY`.
- Google-ключ: `google_api_key.txt` или env `GOOGLE_API_KEY`/`GEMINI_API_KEY`. Модель — `PHOTO_GOOGLE_MODEL`, размер (`512`/`1K`/`2K`/`4K`) — `PHOTO_GOOGLE_SIZE` (по умолчанию `1K`).
- Cloudflare: env `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` приоритетнее `cloudflare.json`.
- `models\edsr-x2.onnx` — ручной апскейл ×2 (по умолчанию в GUI и CLI); `models\realesr-general-x4v3.onnx` — апскейл ×4; `models\faceparser.onnx` — маска волос (только для `hair`).
- Кратность ручного апскейла: `QSettings` → `upscale/factor` (вкладка «Апскейл», 2 или 4), CLI `--factor 2|4`; ядро `upscale(..., factor=...)`. Внутренняя доводка размеров фона в `backgrounds.py` всегда вызывает `upscale()` без factor, то есть остаётся на ×4 — не привязывать её к пользовательской настройке.
- Модель EDSR ×2 взята из `rupeshs/edsr-onnx` — в репозитории не указана лицензия (локальное использование допустимо, для публикации уточнить).
