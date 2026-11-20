"""Photo pipeline for the OpenCode photo plugin.

Commands:
  cut       <source> <out.png> [--model ...] [--no-portrait] [--tile 1024] [--overlap 0.5]
            [--sigma 1.4] [--head-ratio 0.34] [--levels-lo 0.1] [--levels-hi 0.9]
            [--detail-gain 7] [--detail-blur 2.5] [--detail-weight 0.6]
            [--head-blur 6] [--head-weight 0.6] [--no-matting]
            [--no-global-shape] [--global-min-fraction 0.001] [--global-feather 3]
            [--no-stabilize] [--stabilize-min-mid 0.03] [--stabilize-noisy-mid 0.1]
            [--stabilize-min-comps 50] [--stabilize-keep-ratio 0.02]
            [--stabilize-dilate 7] [--stabilize-inner 3]
            [--no-isolated] [--isolated-ratio 0.15] [--isolated-gap 24] [--isolated-halo 32]
            [--no-fill-holes] [--hole-min-area 250] [--hole-max-area 60000]
            [--hole-top-fraction 0.5]
            [--no-hair-refine] [--hair-top-fraction 0.30] [--hair-min-mid 25000]
            [--hair-gain 3.0]
            [--no-color-gaps] [--color-gap-lo 45] [--color-gap-hi 100]
            [--color-gap-top-fraction 0.35] [--color-gap-min-blue 25]
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
from src.core.cut_params import CUT_DEFAULTS  # noqa: E402
from src.core.cutout import make_cutout, recolor_hair  # noqa: E402
from src.core.image import _blur, _levels, _read, _write, analyze  # noqa: E402, F401 — обратная совместимость
from src.core.settings import ESR_MODEL, normalize_factor  # noqa: E402, F401 — обратная совместимость
from src.core.upscale import upscale  # noqa: E402


def cut_params(opts):
    """Собрать параметры вырезки из CLI-флагов.

    Имена флагов — ``cut/*`` без префикса, подчёркивания заменены на дефисы.
    Булевы параметры задаются парой ``--no-*`` (выключить), остальные — значением.
    """
    params = dict(CUT_DEFAULTS)
    for key, flag in (
        ("portrait", "no-portrait"),
        ("matting", "no-matting"),
        ("global_shape", "no-global-shape"),
        ("stabilize", "no-stabilize"),
        ("isolated", "no-isolated"),
        ("fill_holes", "no-fill-holes"),
        ("hair_refine", "no-hair-refine"),
        ("color_gaps", "no-color-gaps"),
    ):
        params[key] = opts.get(flag) != "true"
    ints = {"tile", "stabilize_min_comps", "stabilize_dilate", "stabilize_inner",
            "isolated_gap", "isolated_halo", "hole_min_area", "hole_max_area",
            "hair_min_mid"}
    for key in params:
        if key in {"portrait", "matting", "global_shape", "stabilize", "isolated",
                   "fill_holes", "hair_refine", "color_gaps"}:
            continue
        raw = opts.get(key.replace("_", "-"))
        if raw is None:
            continue
        try:
            params[key] = int(raw) if key in ints else float(raw)
        except (TypeError, ValueError):
            pass
    return params


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
        params = cut_params(opts)
        cut = make_cutout(pos[0], model=opts.get("model"), params=params)
        _write(pos[1], cut)
        a = cut[:, :, 3]
        print(
            f"вырезка: {pos[1]} {cut.shape[1]}x{cut.shape[0]}, "
            f"прозрачно {(a==0).mean()*100:.1f}%, "
            f"обособленные: {'вкл' if params['isolated'] else 'выкл'}, "
            f"волосы: {'вкл' if params['hair_refine'] else 'выкл'}, "
            f"просветы: {'вкл' if params['color_gaps'] else 'выкл'}"
        )
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
