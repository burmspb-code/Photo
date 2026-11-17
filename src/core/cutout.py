"""Вырезка объекта (BiRefNet + pymatting) и маска волос."""
from __future__ import annotations

import cv2
import numpy as np

# Импорт settings применяет IPv4-патч до загрузки rembg.
from src.core.settings import FACE_MODEL, HAIR_COLORS
from rembg import remove, new_session
from pymatting import estimate_foreground_ml

from src.core.image import _blur, _levels, _read, _write

_session = None


def get_session():
    global _session
    if _session is None:
        _session = new_session("birefnet-general")
    return _session


def tiled_alpha(orig, tile=1024):
    H, W = orig.shape[:2]
    xs = [0, W - tile] if W > tile else [0]
    ys = [0, H - tile] if H > tile else [0]
    acc = np.zeros((H, W), np.float32)
    wsum = np.zeros((H, W), np.float32)
    sess = get_session()
    for ty in ys:
        for tx in xs:
            x0, y0 = max(0, tx), max(0, ty)
            y1, x1 = min(H, y0 + tile), min(W, x0 + tile)
            crop = orig[y0:y1, x0:x1]
            th, tw = crop.shape[:2]
            padded = cv2.copyMakeBorder(crop, 0, tile - th, 0, tile - tw, cv2.BORDER_REPLICATE)
            buf = cv2.imencode(".png", padded)[1]
            a = cv2.imdecode(np.frombuffer(remove(buf.tobytes(), session=sess, alpha_matting=False), np.uint8),
                             cv2.IMREAD_UNCHANGED)[:, :, 3].astype(np.float32) / 255.0
            a = a[:th, :tw]
            wgt = np.maximum(np.outer(np.hanning(max(th, 2)), np.hanning(max(tw, 2))).astype(np.float32), 1e-3)
            acc[y0:y1, x0:x1] += a * wgt
            wsum[y0:y1, x0:x1] += wgt
    return np.clip(acc / np.maximum(wsum, 1e-6), 0, 1)


def refine_alpha(a_raw, portrait=True, head_ratio=0.34, sigma=1.4):
    a = _levels(a_raw, 0.10, 0.90)
    w_det = _blur(np.clip(np.abs(a - _blur(a, 2.5)) * 7, 0, 1), 2)
    w = w_det
    if portrait:
        m = a > 0.5
        ys, xs = np.nonzero(m)
        if len(xs):
            y_top, y_bot = ys.min(), ys.max()
            x_lo, x_hi = xs.min(), xs.max()
            head = np.zeros_like(a)
            head[y_top:y_top + int(head_ratio * (y_bot - y_top)), x_lo:x_hi + 1] = 1.0
            w = np.clip(_blur(head, 6) * (a > 0.02) * 0.6 + w_det * 0.6, 0, 1)
    return np.clip(a * (1 - w) + _blur(a, sigma) * w, 0, 1)


def make_cutout(src, portrait=True):
    orig = _read(src)
    if orig.ndim == 2:
        orig = cv2.cvtColor(orig, cv2.COLOR_GRAY2BGR)
    orig = orig[:, :, :3]
    alpha = refine_alpha(tiled_alpha(orig), portrait=portrait)
    F = estimate_foreground_ml(orig.astype(np.float64) / 255.0, alpha.astype(np.float64),
                               return_background=False)
    rgb = np.clip(F * 255, 0, 255).astype(np.uint8)
    return np.dstack([rgb, (alpha * 255).astype(np.uint8)])


def _head_crop(orig, alpha):
    m = alpha > 0.5
    ys, xs = np.nonzero(m)
    if not len(xs):
        return orig, 0, 0, 0
    y_top, y_bot = ys.min(), ys.max()
    x_lo, x_hi = xs.min(), xs.max()
    subj_h = y_bot - y_top
    y_row = min(y_top + int(0.12 * subj_h), y_bot)
    idx = np.nonzero(m[y_row])[0]
    hx0, hx1 = (idx.min(), idx.max()) if len(idx) else (x_lo, x_hi)
    head_w = max(hx1 - hx0, 40)
    cx = (hx0 + hx1) // 2
    side = min(int(head_w * 1.55), min(orig.shape[:2]))
    y0 = max(0, y_top - int(0.10 * head_w))
    x0 = max(0, cx - side // 2)
    x0 = min(x0, orig.shape[1] - side)
    y0 = min(y0, orig.shape[0] - side)
    return orig[y0:y0 + side, x0:x0 + side], x0, y0, side


def hair_mask(orig, alpha):
    crop, x0, y0, side = _head_crop(orig, alpha)
    if side == 0 or not FACE_MODEL.exists():
        return np.zeros(alpha.shape, np.float32)
    import onnxruntime as ort
    sess = ort.InferenceSession(str(FACE_MODEL), providers=["CPUExecutionProvider"])
    inp = cv2.resize(crop, (512, 512))
    x = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    logits = sess.run(None, {sess.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    cls = logits.argmax(0)
    hair = np.isin(cls, [16, 17]).astype(np.float32)
    hair = cv2.resize(hair, (side, side), interpolation=cv2.INTER_LINEAR)
    full = np.zeros(alpha.shape, np.float32)
    full[y0:y0 + side, x0:x0 + side] = hair
    full *= (alpha > 0.5).astype(np.float32)
    return _blur(full, 2.0)


def recolor_hair(src, out, color="rusy", strength=0.85):
    orig = _read(src)
    if orig.shape[2] == 4:
        alpha = orig[:, :, 3].astype(np.float32) / 255.0
        rgb = orig[:, :, :3]
    else:
        rgb = orig[:, :, :3]
        cut = make_cutout(src, portrait=True)
        alpha = cut[:, :, 3].astype(np.float32) / 255.0
        rgb = cut[:, :, :3]
    mask = hair_mask(rgb, alpha) * max(0.0, min(1.0, strength))
    if mask.max() <= 0:
        raise RuntimeError("маска волос не найдена")
    target = HAIR_COLORS.get(color, HAIR_COLORS["rusy"])
    t_lab = cv2.cvtColor(np.uint8([[list(target)]]), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)

    lab = cv2.cvtColor(rgb, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = cv2.split(lab)
    sel = mask > 0.5
    if sel.sum() < 10:
        raise RuntimeError("маска волос слишком мала")
    mL, _mA, _mB = L[sel].mean(), A[sel].mean(), B[sel].mean()
    L2 = L * (t_lab[0] / max(mL, 1))
    L2 = L * 0.15 + L2 * 0.85
    A2 = A * 0.35 + t_lab[1] * 0.65
    B2 = B * 0.35 + t_lab[2] * 0.65
    new = cv2.cvtColor(np.clip(np.dstack([L2, A2, B2]), 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
    w = mask[..., None]
    out_img = np.clip(rgb.astype(np.float32) * (1 - w) + new.astype(np.float32) * w, 0, 255).astype(np.uint8)
    _write(out, out_img)
    print(f"волосы перекрашены: {out} (цвет {color}, маска {sel.mean()*100:.1f}% кадра)", flush=True)
