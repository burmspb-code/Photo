"""Сборка композита: кадрирование фона, тон, тень и зерно."""
from __future__ import annotations

import cv2
import numpy as np

from src.core.image import _blur
from src.core.progress import check_cancel, maybe_report


def _cover(img, w, h):
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih)
    r = cv2.resize(img, (round(iw * s), round(ih * s)), interpolation=cv2.INTER_LANCZOS4)
    y = (r.shape[0] - h) // 2
    x = (r.shape[1] - w) // 2
    return r[y:y + h, x:x + w]


def _tone_match(bg, rgb, alpha, tone):
    m = alpha > 0.8
    lab_s = cv2.cvtColor(rgb, cv2.COLOR_BGR2LAB).astype(np.float32)
    Ls = cv2.split(lab_s)[0][m].mean() if m.any() else 110
    lab = cv2.cvtColor(bg, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = cv2.split(lab)
    L = L * (min(150.0, Ls * tone) / max(L.mean(), 1))
    lab = np.clip(np.dstack([L, A - 1.0, B - 2.5]), 0, 255).astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR).astype(np.float32)


def composite(cut, bg_path, tone=1.06, shadow=0.22, grain=4.5, blur_bg=2.0, seed=7,
              progress=None, cancelled=None):
    check_cancel(cancelled)
    H, W = cut.shape[:2]
    rgb = cut[:, :, :3]
    alpha = cut[:, :, 3].astype(np.float32) / 255.0
    maybe_report(progress, 10, "Чтение фона")
    bg = cv2.imdecode(np.fromfile(str(bg_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    bg = cv2.GaussianBlur(_cover(bg, W, H), (0, 0), blur_bg)
    bg = _tone_match(bg, rgb, alpha, tone)
    maybe_report(progress, 40, "Подгонка тона")
    bg = np.clip(bg * np.linspace(1.05, 0.94, W, dtype=np.float32)[None, :, None], 0, 255)
    ao = np.roll(_blur(alpha, 45), 12, axis=1)
    ao = np.roll(ao, 6, axis=0)
    bg = bg * (1 - shadow * ao[..., None])
    maybe_report(progress, 65, "Контактная тень")
    out = bg * (1 - alpha[..., None]) + rgb.astype(np.float32) * alpha[..., None]
    edge = np.clip(_blur(alpha, 5) - alpha, 0, 1) * 0.3
    out = out * (1 - edge[..., None]) + _blur(bg, 10) * edge[..., None]
    maybe_report(progress, 85, "Зерно")
    rng = np.random.default_rng(seed)
    check_cancel(cancelled)
    result = np.clip(out + rng.normal(0, grain, out.shape), 0, 255).astype(np.uint8)
    maybe_report(progress, 100, "Композит готов")
    return result
