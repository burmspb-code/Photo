"""Вырезка объекта (BiRefNet + pymatting) и маска волос."""
from __future__ import annotations

import cv2
import numpy as np

# Импорт settings применяет IPv4-патч до загрузки rembg.
from src.core.settings import FACE_MODEL, HAIR_COLORS
from rembg import remove, new_session
from pymatting import estimate_foreground_ml

from src.core.image import _blur, _levels, _read, _write
from src.core.progress import check_cancel, maybe_report, scaled

_session = None
_session_model = None


def get_session(model=None):
    global _session, _session_model
    model = model or "birefnet-general"
    if _session is None or _session_model != model:
        _session = new_session(model)
        _session_model = model
    return _session


def tiling_plan(H, W, tile=1024):
    """Позиции тайлов, покрывающие кадр целиком.

    Для кадров до ``2 * tile`` на сторону сохраняется старая схема ровно двух
    тайлов — она даёт побайтово тот же результат, что и утверждённая вырезка.
    Для больших кадров строится сетка с шагом ``tile // 2`` (50 % перекрытия);
    последний тайл всегда прижимается к краю, чтобы не оставалось непокрытых
    полос.
    """
    def axis(size: int) -> list[int]:
        if size <= tile:
            return [0]
        last = size - tile
        if last <= tile:
            return [0, last]  # унаследованное поведение: 2 тайла с перекрытием
        stride = max(1, tile // 2)
        pos = list(range(0, last + 1, stride))
        if pos[-1] != last:
            if last - pos[-1] < stride // 2:
                pos[-1] = last  # почти дубль — сдвигаем последний тайл к краю
            else:
                pos.append(last)
        return pos

    return axis(W), axis(H)


def cut_advisory(src, tile=1024) -> list[str]:
    """Предупреждения о кадре, где автоматическая вырезка может быть плохой."""
    img = _read(src)
    if img is None:
        return []
    h, w = img.shape[:2]
    xs, ys = tiling_plan(h, w, tile)
    notes = []
    if len(xs) * len(ys) > 4:
        notes.append(
            f"Большой кадр {w}×{h}: вырезка пойдёт {len(xs)}×{len(ys)} = "
            f"{len(xs) * len(ys)} тайлами — проверьте швы между ними."
        )
    gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
    contrast = float(gray.std())
    if contrast < 45:
        notes.append(
            f"Низкий контраст (σ={contrast:.0f}): модель может захватить фон. "
            "Проверьте результат; при необходимости обрежьте кадр вокруг объекта."
        )
    return notes


def _tile_with_context(orig, x0, y0, x1, y1, tile, sess):
    """Повторная сегментация тайла с захватом соседних областей.

    Тайл без объекта иногда сегментируется целиком как передний план: модель
    не видит ни одного фрагмента объекта в кадре и возвращает почти сплошную маску.
    Добавляем по ``tile // 2`` пикселей вокруг, прогоняем модель и вырезаем
    исходную область — соседние части объекта дают модели нужный контекст.
    """
    H, W = orig.shape[:2]
    pad = tile // 2
    cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
    cx1, cy1 = min(W, x1 + pad), min(H, y1 + pad)
    crop = orig[cy0:cy1, cx0:cx1]
    ch, cw = crop.shape[:2]
    scale = min(1.0, tile / max(ch, cw))
    if scale < 1.0:
        small = cv2.resize(crop, (max(1, int(cw * scale)), max(1, int(ch * scale))),
                           interpolation=cv2.INTER_AREA)
    else:
        small = crop
    buf = cv2.imencode(".png", small)[1]
    raw = remove(buf.tobytes(), session=sess, alpha_matting=False)
    alpha = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)[:, :, 3]
    if scale < 1.0:
        alpha = cv2.resize(alpha, (cw, ch), interpolation=cv2.INTER_LINEAR)
    return alpha[y0 - cy0:y1 - cy0, x0 - cx0:x1 - cx0].astype(np.float32) / 255.0


def tiled_alpha(orig, tile=1024, model=None, progress=None, cancelled=None):
    H, W = orig.shape[:2]
    xs, ys = tiling_plan(H, W, tile)
    acc = np.zeros((H, W), np.float32)
    wsum = np.zeros((H, W), np.float32)
    sess = get_session(model)
    total = len(xs) * len(ys)
    done = 0
    for ty in ys:
        for tx in xs:
            check_cancel(cancelled)
            x0, y0 = max(0, tx), max(0, ty)
            y1, x1 = min(H, y0 + tile), min(W, x0 + tile)
            crop = orig[y0:y1, x0:x1]
            th, tw = crop.shape[:2]
            padded = cv2.copyMakeBorder(crop, 0, tile - th, 0, tile - tw, cv2.BORDER_REPLICATE)
            buf = cv2.imencode(".png", padded)[1]
            a = cv2.imdecode(np.frombuffer(remove(buf.tobytes(), session=sess, alpha_matting=False), np.uint8),
                             cv2.IMREAD_UNCHANGED)[:, :, 3].astype(np.float32) / 255.0
            a = a[:th, :tw]
            if float((a > 0.5).mean()) > 0.9:
                # Почти сплошная маска — модель не нашла объект в этом тайле.
                a = _tile_with_context(orig, x0, y0, x1, y1, tile, sess)
            wgt = np.maximum(np.outer(np.hanning(max(th, 2)), np.hanning(max(tw, 2))).astype(np.float32), 1e-3)
            acc[y0:y1, x0:x1] += a * wgt
            wsum[y0:y1, x0:x1] += wgt
            done += 1
            maybe_report(progress, done * 100 // total, f"Сегментация {done}/{total}")
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


def global_shape_alpha(orig, model=None, cancelled=None):
    """Ранний H-рецепт: сегментация всего кадра одним проходом модели.

    Тайлы дают детали и лечат отдельные сбойные участки, но на больших кадрах
    могут «потерять» нижнюю часть объекта. Цельный кадр используется как
    страховка: он возвращает пропущенные области без изменения цвета (масштаб
    альфы 8…247, жёсткие пороги и медиана 3 — как в первом рабочем рецепте).
    """
    check_cancel(cancelled)
    buf = cv2.imencode(".png", orig)[1]
    raw = remove(buf.tobytes(), session=get_session(model), alpha_matting=False)
    got = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    a = got[:, :, 3]
    if a.shape != orig.shape[:2]:
        a = cv2.resize(a, (orig.shape[1], orig.shape[0]), interpolation=cv2.INTER_LINEAR)
    stretch = np.clip((a.astype(np.float32) - 8.0) / (247.0 - 8.0) * 255.0, 0, 255)
    stretch[stretch >= 250] = 255
    stretch[stretch <= 5] = 0
    return cv2.medianBlur(stretch.astype(np.uint8), 3).astype(np.float32) / 255.0


def merge_global_shape(alpha, whole, min_fraction=0.001, feather=3.0):
    """Добавить к тайловой альфе области, уверенно найденные на целом кадре.

    Заполняются только пиксели, где цельный кадр почти непрозрачен (>0,9),
    а тайлы почти прозрачны (<0,5). Если таких пикселей меньше 0,1 % кадра,
    маска не меняется — это защищает мелкие артефакты и утверждённый результат.
    """
    fill = ((whole > 0.9) & (alpha < 0.5)).astype(np.float32)
    if float(fill.mean()) < min_fraction:
        return alpha
    weight = cv2.GaussianBlur(fill, (0, 0), feather)
    weight = np.clip(weight * 1.5, 0, 1)[:, :, None]
    target = whole[:, :, None] * weight
    return np.clip(alpha[:, :, None] + (1 - alpha[:, :, None]) * target, 0, 1)[:, :, 0]


def make_cutout(src, portrait=True, model=None, tile=1024, sigma=1.4, head_ratio=0.34,
                matting=True, progress=None, cancelled=None):
    maybe_report(progress, 0, "Чтение изображения")
    orig = _read(src)
    if orig.ndim == 2:
        orig = cv2.cvtColor(orig, cv2.COLOR_GRAY2BGR)
    orig = orig[:, :, :3]
    raw = tiled_alpha(orig, tile=tile, model=model,
                      progress=scaled(progress, 0, 70), cancelled=cancelled)
    maybe_report(progress, 72, "Проверка целого кадра")
    whole = global_shape_alpha(orig, model=model, cancelled=cancelled)
    maybe_report(progress, 75, "Уточнение кромки")
    alpha = refine_alpha(raw, portrait=portrait, head_ratio=head_ratio, sigma=sigma)
    alpha = merge_global_shape(alpha, whole)
    check_cancel(cancelled)
    if matting:
        maybe_report(progress, 85, "Восстановление цвета")
        F = estimate_foreground_ml(orig.astype(np.float64) / 255.0, alpha.astype(np.float64),
                                   return_background=False)
        rgb = np.clip(F * 255, 0, 255).astype(np.uint8)
    else:
        maybe_report(progress, 85, "Без pymatting")
        rgb = orig
    maybe_report(progress, 100, "Вырезка готова")
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
