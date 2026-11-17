# 04. Результат 2026-11-17, вариант C

Утверждённый результат: портрет на фоне тихого городского парка с низким солнцем справа. Пользователь оценил визуально положительно, правки не требовались.

## Карточка

| Поле | Значение |
|---|---|
| Дата фиксации | 2026-11-17 |
| Папка | `data/results/2026-11-17-park-c/` |
| Итог | `final.jpg`, 1632×1224, RGB, JPEG |
| Исходник | `C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG`, 1632×1224 |
| Вырезка | `cutout.png`, 1632×1224, RGBA |
| Провайдер фона | Cloudflare Workers AI |
| Модель | `@cf/black-forest-labs/flux-1-schnell`, 4 шага |
| Фон-источник | `background-source.jpg`, 1024×768 |
| Фон после апскейла | `background-4x.jpg`, 4096×3072 |
| Сравнение | `compare.jpg`, «до / после» |
| Перекраска волос | не выполнялась |

## Промпт

```text
photorealistic quiet city park in late afternoon, low golden sun from the right,
backlit oak trees, long shadows, wooden bench, grass and path, realistic photo, no people
```

Солнце в кадр не попадает: свет читается по подсвеченным кронам и мягким теням на земле. Это осознанный компромисс — на будущее приоритет у фонов вообще без источника света (см. [03-backgrounds.md](03-backgrounds.md#правило-выбора-фона-по-свету)).

## Команды

```powershell
$root = "C:\My_projects\Photo"
$data = "$root\data"
$py = "$root\.venv\Scripts\python.exe"
$pp = "$root\src\photo_pipeline.py"
Set-Location $root

# 1. Вырезка (1–2 минуты)
& $py $pp cut "C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG" "$data\DSC00103-cut.png"

# 2. Черновики фона, без апскейла
& $py $pp genbg "photorealistic quiet city park in late afternoon, low golden sun from the right, backlit oak trees, long shadows, wooden bench, grass and path, realistic photo, no people" "$data\bg\park-flux-c.jpg" --provider cloudflare --no-upscale

# 3. Контактный лист для сравнения A / B / C
& $py "$root\src\contact_sheet.py" "$data\bg\park-flux-draft.jpg" "$data\bg\park-flux-b.jpg" "$data\bg\park-flux-c.jpg" --labels A B C --out "$data\bg\drafts-compare.jpg"

# 4. Апскейл выбранного фона
& $py $pp upscale "$data\bg\park-flux-c.jpg" "$data\bg\park-flux-c-4x.jpg"

# 5. Композит
& $py $pp composite "$data\DSC00103-cut.png" "$data\bg\park-flux-c-4x.jpg" "$data\DSC00103-park-c.jpg" --blur 0.5

# 6. Сравнение «до / после»
& $py "$root\src\contact_sheet.py" "C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG" "$data\DSC00103-park-c.jpg" --labels "ДО" "ПОСЛЕ" --out "$data\DSC00103-park-c-compare.jpg"
```

## Параметры композита

| Параметр | Значение | Зачем |
|---|---:|---|
| `--blur` | 0.5 | Апскейленный фон без размытия выглядит мыльным |
| `--shadow` | 0.22 | Базовая контактная тень, объект не «висит» |
| `--tone` | 1.06 | Лёгкая подгонка яркости фона под портрет |
| `--grain` | 4.5 | Зерно, сопоставимое с исходным снимком |

Выходной размер равен размеру вырезки: 1632×1224 (4:3).

## Файлы и SHA-256

| Файл | Размер, байт | Разрешение | SHA-256 |
|---|---:|---|---|
| `final.jpg` | 701 404 | 1632×1224 | `61573f599a782dfbe5c6a302447c701659d5d77baf3f0a3604717c0da922463f` |
| `compare.jpg` | 319 703 | 1646×648 | `8df319ba3a70b7bbdc925ba312e20827980e34e03680d36be8ed5a09cdc7b5b3` |
| `source.jpg` | 248 266 | 1632×1224 | `1a0ea2d44e1c26b758c630a2ed35275ce238cb5d54fabf80dbd0004ffd5a0049` |
| `cutout.png` | 1 896 793 | 1632×1224 | `682c29222989ea741265317d010a9b9e61ca54eed99c479d63d484cd049f396e` |
| `background-source.jpg` | 308 268 | 1024×768 | `f8747cdf2bff9589c9c68d18481fd5fbe90216c270336ad99996a3ba784909e4` |
| `background-4x.jpg` | 3 477 934 | 4096×3072 | `fe6a9d5970a763aeb6204332e2df8e6aa772ef321b6caac63e49f28248d9adc9` |

Проверка целостности:

```powershell
Get-ChildItem "$data\results\2026-11-17-park-c" -File | ForEach-Object {
  "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
}
```

## Проверка по чек-листу

- [x] свет и тени согласованы с портретом — солнце справа, тени мягкие;
- [x] горизонт на правдоподобном уровне;
- [x] масштаб деревьев и скамейки не игрушечный;
- [x] по контуру волос нет светлого или цветного ободка;
- [x] цвет кожи не ушёл в зелень или оранжевый;
- [x] зерно фона сопоставимо с портретом;
- [x] в фоне нет людей, текста и явных артефактов;
- [x] итог 1632×1224, JPEG, размер исходника.

## Замечания на будущее

- Фон 1024 px + апскейл ×4 даёт приемлемую, но не идеальную детализацию в глубине кадра. Если появится биллинг Google — генерировать сразу 2K/4K.
- Видимое направление света на фоне — потенциальный источник брака. Следующие фоны выбирать без источника в кадре.
- Вырезка `cutout.png` переиспользуется: при замене только фона её не нужно делать заново (1–2 минуты экономии).

## Переезд проекта

2026-11-17 папка перенесена из `C:\Users\bur_s\OneDrive\Documents\Фото` в `C:\My_projects\Photo` и переструктурирована: изображения — в `data\`, код — в `src\`, результаты — в `data\results\`. Содержимое `data\results\2026-11-17-park-c\` не менялось, SHA-256 всех файлов совпадают с исходной фиксацией.
