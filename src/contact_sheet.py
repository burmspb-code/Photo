"""Собирает контактный лист из изображений с подписями.

Пример (из корня проекта):
  python src\\contact_sheet.py "data\\bg\\a.jpg" "data\\bg\\b.jpg" --labels A B --out "data\\bg\\compare.jpg"
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("arialbd.ttf", "arial.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    parser = argparse.ArgumentParser(description="Контактный лист с подписями")
    parser.add_argument("images", nargs="+", help="Входные изображения")
    parser.add_argument("--labels", nargs="*", default=None, help="Подписи (по умолчанию — имена файлов)")
    parser.add_argument("--out", required=True, help="Путь к итоговому JPG")
    parser.add_argument("--width", type=int, default=512, help="Ширина превью (по умолчанию 512)")
    parser.add_argument("--label-height", type=int, default=36)
    parser.add_argument("--gap", type=int, default=12)
    args = parser.parse_args()

    paths = [Path(p) for p in args.images]
    for path in paths:
        if not path.exists():
            raise SystemExit(f"нет файла: {path}")

    labels = list(args.labels or [])
    if len(labels) < len(paths):
        labels += [p.stem for p in paths[len(labels):]]

    thumbs = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        height = max(1, round(args.width * image.height / image.width))
        thumbs.append(image.resize((args.width, height), Image.LANCZOS))

    thumb_height = min(t.height for t in thumbs)
    thumbs = [t.resize((args.width, thumb_height), Image.LANCZOS) for t in thumbs]

    font = load_font(max(16, args.label_height - 10))
    sheet = Image.new(
        "RGB",
        (len(thumbs) * args.width + (len(thumbs) - 1) * args.gap, thumb_height + args.label_height),
        (24, 24, 24),
    )
    draw = ImageDraw.Draw(sheet)
    for i, (thumb, label) in enumerate(zip(thumbs, labels[: len(thumbs)], strict=False)):
        x = i * (args.width + args.gap)
        sheet.paste(thumb, (x, args.label_height))
        draw.text((x + 12, 6), label, font=font, fill=(255, 255, 255))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=92)
    print(f"контактный лист: {out} {sheet.width}x{sheet.height}")


if __name__ == "__main__":
    main()
