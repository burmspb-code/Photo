"""Апскейл: EDSR ×2 или realesr-general-x4v3 ×4."""
from __future__ import annotations

import cv2
import numpy as np

from src.core.image import _read, _write
from src.core.progress import check_cancel, maybe_report
from src.core.settings import EDSR_X2_MODEL, ESR_MODEL, normalize_factor


def _session(factor: int):
    import onnxruntime as ort
    model = EDSR_X2_MODEL if factor == 2 else ESR_MODEL
    return ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])


def _run(sess, img, factor: int, pad: int = 16):
    h, w = img.shape[:2]
    padded = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REFLECT)
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    y = sess.run(None, {sess.get_inputs()[0].name: rgb.transpose(2, 0, 1)[None]})[0][0]
    out = np.clip(y.transpose(1, 2, 0), 0, 1)
    out = cv2.cvtColor((out * 255).round().astype(np.uint8), cv2.COLOR_RGB2BGR)
    k = pad * factor
    return out[k:k + h * factor, k:k + w * factor]


def upscale(src, out, tile=512, overlap=32, quality=95, factor=4,
            progress=None, cancelled=None):
    factor = normalize_factor(factor)
    maybe_report(progress, 0, "Чтение изображения")
    img = _read(src)[:, :, :3]
    check_cancel(cancelled)
    maybe_report(progress, 10, "Загрузка модели")
    sess = _session(factor)
    h, w = img.shape[:2]
    if h * w <= 600_000:
        check_cancel(cancelled)
        maybe_report(progress, 50, "Апскейл")
        res = _run(sess, img, factor)
    else:
        res = np.zeros((h * factor, w * factor, 3), np.uint8)
        step = tile
        rows = range(0, h, step)
        cols = range(0, w, step)
        total = len(rows) * len(cols)
        done = 0
        for y in rows:
            for x in cols:
                check_cancel(cancelled)
                y0, x0 = max(0, y - overlap), max(0, x - overlap)
                y1, x1 = min(h, y + tile + overlap), min(w, x + tile + overlap)
                up = _run(sess, img[y0:y1, x0:x1], factor)
                ch, cw = min(h, y + tile) - y, min(w, x + tile) - x
                oy, ox = (y - y0) * factor, (x - x0) * factor
                res[y * factor:(y + ch) * factor, x * factor:(x + cw) * factor] = \
                    up[oy:oy + ch * factor, ox:ox + cw * factor]
                done += 1
                maybe_report(progress, 10 + done * 80 // total, f"Тайл {done}/{total}")
    check_cancel(cancelled)
    maybe_report(progress, 95, "Сохранение")
    _write(out, res, quality)
    maybe_report(progress, 100, "Апскейл готов")
    print(f"апскейл ×{factor}: {out} {res.shape[1]}x{res.shape[0]}", flush=True)
