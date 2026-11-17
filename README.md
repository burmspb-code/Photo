# Photo

Проект обработки фотографий: вырезка объекта, генерация и замена фона, апскейл и композит.

- Корень: `C:\My_projects\Photo`
- Данные: `data\` (черновики — `data\bg\`, утверждённые результаты — `data\results\`)
- Код: `src\photo_pipeline.py`, `src\contact_sheet.py`
- Модели: `models\` (ONNX)
- Документация: [docs/README.md](docs/README.md)
- Утверждённый результат: [data/results/2026-11-17-park-c](data/results/2026-11-17-park-c/README.md)

## Быстрый старт

```powershell
$root = "C:\My_projects\Photo"
$data = "$root\data"
$py = "$root\.venv\Scripts\python.exe"
$pp = "$root\src\photo_pipeline.py"
Set-Location $root

& $py $pp cut "C:\Users\bur_s\OneDrive\Изображения\DSC00103.JPG" "$data\DSC00103-cut.png"
& $py $pp genbg "photorealistic quiet park, soft overcast light, no people" "$data\bg\park.jpg" --provider cloudflare --no-upscale
& $py $pp upscale "$data\bg\park.jpg" "$data\bg\park-4x.jpg"
& $py $pp composite "$data\DSC00103-cut.png" "$data\bg\park-4x.jpg" "$data\final.jpg" --blur 0.5
```

## Окружение

- `.venv` — Poetry-окружение (Python 3.14) с зависимостями: rembg, onnxruntime, opencv-python-headless, pillow, pymatting, numpy, scipy.
- Установка: `poetry install`.
- Ключи API хранятся вне проекта, в `%LOCALAPPDATA%\rembg-env\`.
- Плагин `photo-tools` использует `.venv` и `src\photo_pipeline.py`, при их отсутствии откатывается на `rembg-env`.

Подробности: [docs/06-development.md](docs/06-development.md).
