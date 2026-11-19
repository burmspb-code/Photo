"""Photo pipeline for the OpenCode photo plugin.

Commands:
  cut       <source> <out.png> [--no-portrait]
  composite <cutout.png> <background> <out.jpg> [--shadow 0.22] [--tone 1.06] [--grain 4.5] [--blur 2.0]
  hair      <source> <out.jpg|png> [--color rusy] [--strength 0.85]
  analyze   <source>
  genbg     <prompt> <out.jpg> [--width 886] [--height 664] [--seed 7] [--no-upscale]
            [--size 1K|2K|4K]
            [--provider auto|google|cloudflare|stability|huggingface|pollinations] [--model ...]
  upscale   <source> <out.jpg|png> [--factor 2|4]
"""
from __future__ import annotations

import sys
from pathlib import Path

# Запуск напрямую (`python src/photo_pipeline.py ...`) добавляет корень проекта в sys.path,
# чтобы импорты src.core работали и как скрипт, и как модуль (`python -m src.photo_pipeline`).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.core.backgrounds import _aspect, _crop_aspect, genbg  # noqa: E402, F401 — обратная совместимость
from src.core.prompt import prepare_prompt  # noqa: E402 — перевод и обязательная фраза
from src.core.compose import _cover, composite  # noqa: E402, F401 — обратная совместимость
from src.core.cutout import make_cutout, recolor_hair  # noqa: E402
from src.core.image import _blur, _levels, _read, _write, analyze  # noqa: E402, F401 — обратная совместимость
from src.core.settings import ESR_MODEL, normalize_factor  # noqa: E402, F401 — обратная совместимость
from src.core.upscale import upscale  # noqa: E402


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    opts = {}
    pos = []
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            k = args[i][2:]
            v = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else "true"
            opts[k] = v
            i += 2 if v != "true" else 1
        else:
            pos.append(args[i])
            i += 1

    if cmd == "cut":
        cut = make_cutout(pos[0], portrait=opts.get("no-portrait") != "true")
        _write(pos[1], cut)
        a = cut[:, :, 3]
        print(f"вырезка: {pos[1]} {cut.shape[1]}x{cut.shape[0]}, прозрачно {(a==0).mean()*100:.1f}%")
    elif cmd == "composite":
        cut = _read(pos[0])
        if cut.shape[2] == 3:
            raise RuntimeError("нужен PNG с альфа-каналом")
        out = composite(cut, pos[1], shadow=float(opts.get("shadow", 0.22)),
                        tone=float(opts.get("tone", 1.06)), grain=float(opts.get("grain", 4.5)),
                        blur_bg=float(opts.get("blur", 2.0)))
        _write(pos[2], out)
        print(f"композит: {pos[2]}")
    elif cmd == "hair":
        recolor_hair(pos[0], pos[1], color=opts.get("color", "rusy"),
                     strength=float(opts.get("strength", 0.85)))
    elif cmd == "analyze":
        analyze(pos[0])
    elif cmd == "genbg":
        genbg(prepare_prompt(pos[0]), pos[1], int(opts.get("width", 886)), int(opts.get("height", 664)),
              int(opts.get("seed", 7)), do_upscale=opts.get("no-upscale") != "true",
              provider=opts.get("provider", "auto"), model=opts.get("model"),
              size=opts.get("size"))
    elif cmd == "upscale":
        upscale(pos[0], pos[1], factor=normalize_factor(opts.get("factor", 2)))
    else:
        print(f"неизвестная команда: {cmd}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
