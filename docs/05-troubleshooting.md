# 05. Типичные ошибки

## Сеть

### Запрос висит и не завершается

Причина — IPv6 в этой сети. В `src\core\settings.py` стоит патч `socket.getaddrinfo`, который принудительно ходит через IPv4 (при импорте ядра, до загрузки rembg), поэтому сам пайплайн не страдает. Сторонние клиенты патча не имеют.

```powershell
curl.exe -4 -sS "https://api.cloudflare.com/client/v4/"
```

Python без патча и Node `fetch` будут таймаутиться. Лечится только IPv4 или VPN.

### Cloudflare: `WinError 10054` / `Recv failure: Connection was reset`

TCP до `api.cloudflare.com` устанавливается за ~0.04 с, но TLS-handshake срывается через ~19–21 с. Это **фильтрация по SNI** на пути трафика, а не проблема ключа или кода: одинаково рвутся `api.`, `dash.`, `www.cloudflare.com`, `pages.dev`, `cf.com`, `discord.com`, но проходят `https://1.1.1.1`, `workers.dev` и обычные сайты. Проверка (без утечки токена):

```powershell
curl.exe -4 -v --max-time 25 -o NUL https://api.cloudflare.com/client/v4/
# Trying 104.19.192.29:443 -> ALPN offer -> Recv failure: Connection was reset
curl.exe -4 -k -o NUL -w "http=%{http_code} total=%{time_total}" `
  -H "Host: api.cloudflare.com" https://104.19.192.29/client/v4/
# http=404 total=0.2  — без SNI соединение проходит
```

Обход через IP + `Host` для генерации **непригоден**: ответ API приходит (~0.24 с до первого байта), но передача обрывается на ~25 КБ от ~760 КБ (картинка не скачивается). Вариант с чужим разрешённым SNI (`workers.dev`) даёт `403` — Cloudflare роутит по SNI, а не по `Host`.

Лечение — вернуть VPN/exit node, чтобы трафик шёл мимо фильтрующего провайдера. Проверить:

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" exit-node list   # не должно быть "no exit nodes found"
& "C:\Program Files\Tailscale\tailscale.exe" status
netsh winhttp show proxy                                       # при включённом прокси — не "Прямой доступ"
```

В `%USERPROFILE%\AppData\Local\Temp` и реестре `HKCU:\...\Internet Settings` остаётся `ProxyServer = 127.0.0.1:2080` от старого локального прокси; если слушателя на 2080 нет, он не помогает.

### Cloudflare: `Invalid API Token` на `/user/tokens/verify`

Это нормально: токены, созданные под Workers AI, не проходят проверку на общем эндпоинте. Токен при этом рабочий. Проверять запросом к `/accounts/<id>/ai/models/search` или просто сгенерировать картинку.

### Cloudflare: `404` / `model not found`

Модель указана без префикса или устарела. Рабочее имя:

```text
@cf/black-forest-labs/flux-1-schnell
```

### Cloudflare: `Authentication error` / `Unable to authenticate request`

- не включён Workers AI в дашборде;
- у токена нет права `Workers AI: Read`;
- `account_id` и токен от разных аккаунтов;
- `cloudflare.json` лежит не в `%LOCALAPPDATA%\rembg-env\`.

### Hugging Face: `402 Purchase pre-paid credits`

У free-аккаунта HF нет бесплатных кредитов на inference, токен не помогает. Не тратить время, переключаться на Cloudflare.

### Hugging Face: `410 model is deprecated`

Старый маршрут `hf-inference` с `FLUX.1-schnell` отключён. Провайдер HF в этом проекте фактически нерабочий.

### Google: `403` / `billing required`

Imagen отключён, актуальны только Gemini image-модели, а у них нет бесплатного тарифа. Нужен включённый биллинг, ~$0.0336 за 1K-картинку. Без биллинга — Cloudflare.

### Stability: `401` без ключа

Ключа нет. Аккаунт даёт 25 кредитов, но их надо получить отдельно. Не приоритет, пока работает Cloudflare.

## Плагин и скрипт

### Namespace `photo` не появился

1. Смотреть лог: `%USERPROFILE%\.local\share\opencode\log\opencode.log`.
2. Проверить регистрацию в `~/.config/opencode/opencode.json`.
3. Node/npm/bun не установлены — плагин не собирается и не должен; OpenCode загружает TS сам.
4. Если плагин держит старый снапшот кода — использовать CLI, результат идентичен.

### `composite` падает с ошибкой аргументов

Выходной путь обязателен третьим позиционным аргументом:

```powershell
& $py $pp composite "cut.png" "bg.jpg" "final.jpg"
```

Плагин подставляет путь сам, в CLI — вручную.

### `cut` идёт долго

1–2 минуты — норма: тайловый BiRefNet плюс pymatting. Не прерывать. На слабом CPU может быть дольше.

### В вырезке остался замкнутый «пробел»

Если модель оставила внутри объекта прозрачный участок (как на `DSCN1941.jpg` внизу кадра), он восстанавливается по маске цельного кадра: `global_shape_alpha()` и `merge_global_shape()` в `src\core\cutout.py` добавляют только области, где цельный кадр уверенно непрозрачен (>0,9), а тайлы почти прозрачны (<0,5). Цвет берётся из исходника до pymatting, поэтому залитый участок не отличается оттенком. Настоящие зазоры (между руками или ногами), прозрачные и на целом кадре, остаются прозрачными. Если пропуск не восстановился, проверьте альфу цельного кадра — возможно, модель приняла за объект весь нижний фон; в этом случае помогает обрезка кадра перед вырезкой.

### Ошибка чтения файла с кириллицей

В PowerShell путь исходника (`C:\Users\bur_s\OneDrive\Изображения\...`) всегда в кавычках. Путь проекта — `C:\My_projects\Photo`, ASCII. Кракозябры в консоли — только отображение, файлы в UTF-8 корректны.

### `ModuleNotFoundError: No module named 'PIL'` / `cv2` / `numpy`

Зависимости не установлены в текущем интерпретаторе. В проекте они объявлены в `pyproject.toml`:

```powershell
Set-Location "C:\My_projects\Photo"
poetry install
```

Если ошибка появилась при запуске через плагин — проверить, что `.venv\Scripts\python.exe` существует и что `poetry install` завершился без ошибок. Плагин в этом случае может откатиться на `rembg-env`.

### PyCharm: интерпретатор и запуск

- Интерпретатор проекта — `.venv\Scripts\python.exe` (Python 3.14), прописан в `.idea\misc.xml`.
- Он же используется для пайплайна: `rembg`, `onnxruntime`, `opencv`, `pillow`, `pymatting` установлены в `.venv`.
- Run Configuration: script `src\photo_pipeline.py`, working directory — корень проекта, аргументы — как в CLI.
- Встроенный терминал открывается в корне проекта, `Set-Location` не нужен.

### Poetry: `Readme path ... does not exist`

`pyproject.toml` ссылается на `README.md` в корне проекта. Файл должен существовать, иначе `poetry build`/`install` ругаются. В проекте он есть — короткое описание со ссылкой на документацию.

### Плагин не видит проектный скрипт

Плагин выбирает `.venv\Scripts\python.exe` и `src\photo_pipeline.py`, если они существуют; иначе — `rembg-env`. Принудительно задать пути:

```powershell
$env:PHOTO_PROJECT = "C:\My_projects\Photo"
$env:PHOTO_PYTHON = "C:\My_projects\Photo\.venv\Scripts\python.exe"
$env:PHOTO_PIPELINE = "C:\My_projects\Photo\src\photo_pipeline.py"
```

Перезапустить OpenCode после изменения переменных.

### Модели не найдены

Порядок поиска: `PHOTO_MODELS` → `<проект>\models` → `%LOCALAPPDATA%\rembg-env\models`. Проверить, что `models\faceparser.onnx` и `models\realesr-general-x4v3.onnx` на месте. Модель `birefnet-general` не входит в `models\`: rembg скачивает её сам.

### После переезда не находятся файлы

Старые команды и конспекты ссылались на `bg\` и `results\` в корне. Теперь это `data\bg\` и `data\results\`. Проверить, что команда запущена из `C:\My_projects\Photo` и пути начинаются с `data\`.

## Качество результата

| Симптом | Причина | Что делать |
|---|---|---|
| Фон мыльный, «пластиковый» | апскейл ×4 без размытия | `--blur 0.5–0.8` |
| Фон слишком резкий | мало размытия | `--blur` до 1.2 |
| Объект «висит» в воздухе | слабая тень | `--shadow` 0.28–0.3 |
| Фон темнее/светлее портрета | не подогнан тон | `--tone` 0.95–1.12 |
| Фон стерильный | нет зерна | `--grain` 6–8 |
| Светлый или цветной ободок по волосам | плохая вырезка | пересобрать `cut` |
| Тени на земле не совпадают с лицом | в фоне видимый источник света | выбрать фон без источника, перегенерировать |
| Кожа ушла в зелень/оранжевый | неудачный фон или `--tone` | сменить фон, вернуть `--tone` к 1.06 |
| В кадре появились люди | промпт без запрета | добавить `no people, no text` |
| Итог не того размера | фон другого формата | итог всегда равен размеру вырезки; проверить `cutout.png` |

## Диагностика фона

- Контактный лист: `src\contact_sheet.py` — сравнить варианты рядом, а не по памяти.
- Технические параметры снимка: `& $py $pp analyze "photo.jpg"`.
- Проверить, что фон действительно тот: у Cloudflare 1024×1024 до кропа, 1024×768 после; 4096×3072 — после апскейла.
