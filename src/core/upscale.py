"""Апскейл ×4 моделью realesr-general-x4v3."""
from __future__ import annotations

import cv2
import numpy as np

from src.core.image import _read, _write
from src.core.progress import check_cancel, maybe_report
from src.core.settings import ESR_MODEL


def _esr_session():
    import onnxruntime as ort
    return ort.InferenceSession(str(ESR_MODEL), providers=["CPUExecutionProvider"])


def _esr_run(sess, img, pad=16):
    h, w = img.shape[:2]
    padded = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REFLECT)
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    y = sess.run(None, {sess.get_inputs()[0].name: rgb.transpose(2, 0, 1)[None]})[0][0]
    out = np.clip(y.transpose(1, 2, 0), 0, 1)
    out = cv2.cvtColor((out * 255).round().astype(np.uint8), cv2.COLOR_RGB2BGR)
    return out[pad * 4:pad * 4 + h * 4, pad * 4:pad * 4 + w * 4]


def upscale(src, out, tile=512, overlap=32, quality=95, progress=None, cancelled=None):
    maybe_report(progress, 0, "Чтение изображения")
    img = _read(src)[:, :, :3]
    check_cancel(cancelled)
    maybe_report(progress, 10, "Загрузка модели")
    sess = _esr_session()
    h, w = img.shape[:2]
    if h * w <= 600_000:
        check_cancel(cancelled)
        maybe_report(progress, 50, "Апскейл")
        res = _esr_run(sess, img)
    else:
        res = np.zeros((h * 4, w * 4, 3), np.uint8)
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
                up = _esr_run(sess, img[y0:y1, x0:x1])
                ch, cw = min(h, y + tile) - y, min(w, x + tile) - x
                oy, ox = (y - y0) * 4, (x - x0) * 4
                res[y * 4:(y + ch) * 4, x * 4:(x + cw) * 4] = up[oy:oy + ch * 4, ox:ox + cw * 4]
                done += 1
                maybe_report(progress, 10 + done * 80 // total, f"Тайл {done}/{total}")
    check_cancel(cancelled)
    maybe_report(progress, 95, "Сохранение")
    _write(out, res, quality)
    maybe_report(progress, 100, "Апскейл готов")
    print(f"апскейл ×4: {out} {res.shape[1]}x{res.shape[0]}", flush=True)
