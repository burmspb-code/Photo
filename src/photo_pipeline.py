"""Photo pipeline for the OpenCode photo plugin.

Commands:
  cut       <source> <out.png> [--no-portrait]
  composite <cutout.png> <background> <out.jpg> [--shadow 0.22] [--tone 1.06] [--grain 4.5] [--blur 2.0]
  hair      <source> <out.jpg|png> [--color rusy] [--strength 0.85]
  analyze   <source>
  genbg     <prompt> <out.jpg> [--width 886] [--height 664] [--seed 7] [--no-upscale]
            [--provider auto|google|cloudflare|stability|huggingface|pollinations] [--model ...]
  upscale   <source> <out.jpg|png>
"""
import base64
import json
import os
import socket
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import cv2
import numpy as np

# На этой сети IPv6 часто зависает — принудительно предпочитаем IPv4.
_orig_getaddrinfo = socket.getaddrinfo


def _prefer_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    try:
        res = _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        if res:
            return res
    except Exception:  # noqa: S110 — при ошибке пробуем исходный getaddrinfo
        pass
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _prefer_ipv4
from rembg import remove, new_session  # noqa: E402 — патч IPv4 должен быть установлен до импорта
from pymatting import estimate_foreground_ml  # noqa: E402

HERE = Path(__file__).resolve().parent              # src\
PROJECT_ROOT = HERE.parent                          # корень проекта
RUNTIME_DIR = Path(
    os.environ.get("PHOTO_RUNTIME_DIR")
    or (Path(os.environ.get("LOCALAPPDATA", "")) / "rembg-env")
)                                                   # рабочее окружение и ключи


def _model_path(name: str) -> Path:
    r"""Модели: PHOTO_MODELS → <проект>\models → rembg-env\models."""
    env = (os.environ.get("PHOTO_MODELS") or "").strip()
    if env:
        return Path(env) / name
    local = PROJECT_ROOT / "models" / name
    if local.exists():
        return local
    return RUNTIME_DIR / "models" / name


FACE_MODEL = _model_path("faceparser.onnx")
ESR_MODEL = _model_path("realesr-general-x4v3.onnx")
HAIR_COLORS = {
    "rusy": (150, 112, 78),
    "light_brown": (176, 138, 96),
    "blond": (208, 178, 122),
    "platinum": (226, 214, 190),
    "black": (38, 32, 30),
    "dark_brown": (84, 60, 44),
    "red": (150, 74, 48),
}
GOOGLE_KEY_FILE = Path(
    os.environ.get("PHOTO_GOOGLE_KEY_FILE")
    or (Path.home() / ".config" / "opencode" / "photo-tools.json")
)
GOOGLE_KEY_TXT = Path(os.environ.get("PHOTO_GOOGLE_KEY") or (RUNTIME_DIR / "google_api_key.txt"))
CF_CREDS = Path(os.environ.get("PHOTO_CLOUDFLARE_CREDS") or (RUNTIME_DIR / "cloudflare.json"))
HF_TOKEN_TXT = Path(os.environ.get("PHOTO_HF_TOKEN") or (RUNTIME_DIR / "hf_token.txt"))
STABILITY_KEY_TXT = Path(os.environ.get("PHOTO_STABILITY_KEY") or (RUNTIME_DIR / "stability_api_key.txt"))

_session = None


def get_session():
    global _session
    if _session is None:
        _session = new_session("birefnet-general")
    return _session


def _levels(x, lo, hi):
    return np.clip((x - lo) / (hi - lo), 0, 1)


def _blur(a, s):
    return cv2.GaussianBlur(a, (0, 0), s)


def _read(path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)


def _write(path, img, quality=92):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1]
    else:
        buf = cv2.imencode(".png", img)[1]
    buf.tofile(str(path))


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


def composite(cut, bg_path, tone=1.06, shadow=0.22, grain=4.5, blur_bg=2.0, seed=7):
    H, W = cut.shape[:2]
    rgb = cut[:, :, :3]
    alpha = cut[:, :, 3].astype(np.float32) / 255.0
    bg = cv2.imdecode(np.fromfile(str(bg_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    bg = cv2.GaussianBlur(_cover(bg, W, H), (0, 0), blur_bg)
    bg = _tone_match(bg, rgb, alpha, tone)
    bg = np.clip(bg * np.linspace(1.05, 0.94, W, dtype=np.float32)[None, :, None], 0, 255)
    ao = np.roll(_blur(alpha, 45), 12, axis=1)
    ao = np.roll(ao, 6, axis=0)
    bg = bg * (1 - shadow * ao[..., None])
    out = bg * (1 - alpha[..., None]) + rgb.astype(np.float32) * alpha[..., None]
    edge = np.clip(_blur(alpha, 5) - alpha, 0, 1) * 0.3
    out = out * (1 - edge[..., None]) + _blur(bg, 10) * edge[..., None]
    rng = np.random.default_rng(seed)
    return np.clip(out + rng.normal(0, grain, out.shape), 0, 255).astype(np.uint8)


# ---------------- hair ----------------

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


# ---------------- upscale ----------------


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


def upscale(src, out, tile=512, overlap=32, quality=95):
    img = _read(src)[:, :, :3]
    sess = _esr_session()
    h, w = img.shape[:2]
    if h * w <= 600_000:
        res = _esr_run(sess, img)
    else:
        res = np.zeros((h * 4, w * 4, 3), np.uint8)
        step = tile
        for y in range(0, h, step):
            for x in range(0, w, step):
                y0, x0 = max(0, y - overlap), max(0, x - overlap)
                y1, x1 = min(h, y + tile + overlap), min(w, x + tile + overlap)
                up = _esr_run(sess, img[y0:y1, x0:x1])
                ch, cw = min(h, y + tile) - y, min(w, x + tile) - x
                oy, ox = (y - y0) * 4, (x - x0) * 4
                res[y * 4:(y + ch) * 4, x * 4:(x + cw) * 4] = up[oy:oy + ch * 4, ox:ox + cw * 4]
    _write(out, res, quality)
    print(f"апскейл ×4: {out} {res.shape[1]}x{res.shape[0]}", flush=True)


# ---------------- analyze ----------------

def analyze(src):
    from PIL import Image, ExifTags
    p = Path(src)
    im = Image.open(p)
    exif = im.getexif()
    tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
    data = {
        "file": str(p),
        "size": list(im.size),
        "mode": im.mode,
        "bytes": p.stat().st_size,
        "camera": f"{tags.get('Make', '')} {tags.get('Model', '')}".strip() or None,
        "date": str(tags.get("DateTimeOriginal") or tags.get("DateTime") or ""),
        "orientation": tags.get("Orientation"),
        "has_icc": bool(im.info.get("icc_profile")),
    }
    rgb = _read(src)
    if rgb.ndim == 3 and rgb.shape[2] >= 3:
        g = cv2.cvtColor(rgb[:, :, :3], cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([g], [0], None, [256], [0, 256]).ravel()
        n = g.size
        data["luma_mean"] = round(float(g.mean()), 1)
        data["shadows_pct"] = round(float(hist[:16].sum() / n * 100), 1)
        data["highlights_pct"] = round(float(hist[240:].sum() / n * 100), 1)
        data["sharpness"] = round(float(cv2.Laplacian(g, cv2.CV_32F).var()), 1)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cf_creds():
    acc = (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    tok = (os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip()
    if acc and tok:
        return acc, tok
    if CF_CREDS.exists():
        try:
            d = json.loads(CF_CREDS.read_text(encoding="utf-8"))
            return (d.get("account_id") or "").strip(), (d.get("token") or "").strip()
        except Exception:  # noqa: S110 — некорректный файл ключей означает отсутствие ключа
            pass
    return "", ""


def hf_token():
    tok = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
    if tok:
        return tok
    if HF_TOKEN_TXT.exists():
        return HF_TOKEN_TXT.read_text(encoding="utf-8").strip()
    return ""


def _decode_save(raw, out):
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("не удалось декодировать изображение от провайдера")
    _write(out, img)
    return img


def _crop_aspect(img, width, height):
    h, w = img.shape[:2]
    target = width / max(height, 1)
    if abs(w / h - target) < 0.02:
        return img
    if w / h > target:
        nw = int(h * target)
        x = (w - nw) // 2
        return img[:, x:x + nw]
    nh = int(w / target)
    y = (h - nh) // 2
    return img[y:y + nh, :]


def genbg_cloudflare(prompt, out, width=1632, height=1224, model="@cf/black-forest-labs/flux-1-schnell", steps=4):
    acc, tok = cf_creds()
    if not acc or not tok:
        raise RuntimeError("нет ключа Cloudflare: сохраните account_id и token в " + str(CF_CREDS))
    body = json.dumps({"prompt": prompt, "steps": steps}).encode()
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{model}",
        data=body, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:  # noqa: S310 — HTTPS, хост задан константой
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Cloudflare API {e.code}: {msg}") from e
    if not data.get("success"):
        raise RuntimeError(f"Cloudflare API: {json.dumps(data.get('errors'))[:300]}")
    b64 = (data.get("result") or {}).get("image")
    if not b64:
        raise RuntimeError("Cloudflare вернул ответ без изображения")
    img = _decode_save(base64.b64decode(b64), out)
    img = _crop_aspect(img, width, height)
    _write(out, img)
    print(f"Cloudflare ({model}): {out} {img.shape[1]}x{img.shape[0]}", flush=True)
    return model


def genbg_hf(prompt, out, width=1024, height=768, model="black-forest-labs/FLUX.1-schnell"):
    tok = hf_token()
    if not tok:
        raise RuntimeError("нет токена Hugging Face: сохраните его в " + str(HF_TOKEN_TXT))
    payload = {"inputs": prompt, "parameters": {"width": min(width, 1024), "height": min(height, 1024)}}
    req = urllib.request.Request(
        f"https://router.huggingface.co/hf-inference/models/{model}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "Accept": "image/png"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 — HTTPS, хост задан константой
            raw = r.read()
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Hugging Face API {e.code}: {msg}") from e
    if raw[:1] == b"{":
        raise RuntimeError(f"Hugging Face API: {raw[:300].decode('utf-8', 'replace')}")
    img = _decode_save(raw, out)
    img = _crop_aspect(img, width, height)
    _write(out, img)
    print(f"Hugging Face ({model}): {out} {img.shape[1]}x{img.shape[0]}", flush=True)
    return model


def stability_key():
    key = (os.environ.get("STABILITY_API_KEY") or "").strip()
    if key:
        return key
    if STABILITY_KEY_TXT.exists():
        return STABILITY_KEY_TXT.read_text(encoding="utf-8").strip()
    return ""


def _multipart(fields):
    boundary = "----photo" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def genbg_stability(prompt, out, width=1632, height=1224, model=None):
    key = stability_key()
    if not key:
        raise RuntimeError("нет ключа Stability: сохраните его в " + str(STABILITY_KEY_TXT))
    models = [model] if model else ["sd3.5-large", "sd3.5-large-turbo", "sd3.5-medium"]
    errors = []
    for name in models:
        body, boundary = _multipart({
            "prompt": prompt,
            "model": name,
            "aspect_ratio": "3:2",
            "output_format": "jpeg",
            "mode": "text-to-image",
        })
        req = urllib.request.Request(
            "https://api.stability.ai/v2beta/stable-image/generate/sd3",
            data=body,
            headers={"Authorization": f"Bearer {key}", "Accept": "image/*",
                     "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 — HTTPS, хост задан константой
                raw = r.read()
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:400]
            errors.append(f"{name}: {e.code} {msg}")
            print(f"Stability {name}: {e.code} {msg}", flush=True)
            if e.code in (400, 402, 429):
                continue
            raise RuntimeError(f"Stability API {e.code}: {msg}") from e
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"Stability {name}: {e}", flush=True)
            continue
        img = _decode_save(raw, out)
        img = _crop_aspect(img, width, height)
        _write(out, img)
        print(f"Stability ({name}): {out} {img.shape[1]}x{img.shape[0]}", flush=True)
        return name
    raise RuntimeError("Stability: " + "; ".join(errors))


# ---------------- background generation ----------------

def google_key():
    key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if key:
        return key
    if GOOGLE_KEY_TXT.exists():
        return GOOGLE_KEY_TXT.read_text(encoding="utf-8").strip()
    if GOOGLE_KEY_FILE.exists():
        try:
            data = json.loads(GOOGLE_KEY_FILE.read_text(encoding="utf-8"))
            return (data.get("google_api_key") or data.get("api_key") or "").strip()
        except Exception:  # noqa: S110 — некорректный файл ключей означает отсутствие ключа
            pass
    return ""


def _google_json(url, key, payload=None, extra_headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    req = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310 — HTTPS-адреса API
    try:
        with urllib.request.urlopen(req, timeout=240) as r:  # noqa: S310 — HTTPS-адреса API
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body)["error"]["message"]
        except Exception:
            msg = body[:300]
        raise RuntimeError(f"Google API {e.code}: {msg}") from e


def _google_image_model(preferred=None):
    return preferred or os.environ.get("PHOTO_GOOGLE_MODEL") or "gemini-nano-banana-2.1"


def _google_image_b64(data):
    for step in data.get("steps") or []:
        if step.get("type") != "model_output":
            continue
        for block in step.get("content") or []:
            if block.get("type") == "image" and block.get("data"):
                return block["data"]
    block = data.get("output_image") or {}
    if block.get("data"):
        return block["data"]
    raise RuntimeError("Google вернул ответ без изображения")


def _aspect(width, height):
    r = width / max(height, 1)
    if r > 1.45:
        return "16:9"
    if r < 0.7:
        return "9:16"
    if r > 1.1:
        return "4:3"
    if r < 0.9:
        return "3:4"
    return "1:1"


def genbg_google(prompt, out, width=1632, height=1224, model=None, key=None):
    key = key or google_key()
    if not key:
        raise RuntimeError("нет ключа Google AI Studio: задайте GOOGLE_API_KEY или файл "
                           f"{GOOGLE_KEY_TXT}")
    model = _google_image_model(model)
    size = os.environ.get("PHOTO_GOOGLE_SIZE", "1K")
    payload = {
        "model": model,
        "input": [{"type": "text", "text": prompt}],
        "response_format": {
            "type": "image",
            "mime_type": "image/jpeg",
            "aspect_ratio": _aspect(width, height),
            "image_size": size,
        },
    }
    data = _google_json("https://generativelanguage.googleapis.com/v1beta/interactions",
                        key, payload, extra_headers={"Api-Revision": "2026-05-20"})
    raw = base64.b64decode(_google_image_b64(data))
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("не удалось декодировать ответ Google")
    img = _crop_aspect(img, width, height)
    _write(out, img)
    print(f"Google {model}: {out} {img.shape[1]}x{img.shape[0]}", flush=True)
    return model


def genbg(prompt, out, width=886, height=664, seed=7, retries=5, do_upscale=True,
          provider="auto", model=None):
    order = {
        "auto": ["google", "cloudflare", "stability", "huggingface", "pollinations"],
        "google": ["google"],
        "cloudflare": ["cloudflare"],
        "stability": ["stability"],
        "huggingface": ["huggingface"],
        "pollinations": ["pollinations"],
    }.get(provider, ["pollinations"])

    errors = []
    for p in order:
        try:
            if p == "google":
                genbg_google(prompt, out, 1632, 1224, model=model)
            elif p == "cloudflare":
                genbg_cloudflare(prompt, out, 1632, 1224, model=model or "@cf/black-forest-labs/flux-1-schnell")
            elif p == "stability":
                genbg_stability(prompt, out, 1632, 1224, model=model)
            elif p == "huggingface":
                genbg_hf(prompt, out, 1632, 1224, model=model or "black-forest-labs/FLUX.1-schnell")
            else:
                _pollinations(prompt, out, width, height, seed, retries)
            if do_upscale and ESR_MODEL.exists():
                upscale(out, out)
            return
        except Exception as e:
            errors.append(f"{p}: {e}")
            print(f"{p}: {e}", flush=True)
    raise RuntimeError("не удалось сгенерировать фон — " + "; ".join(errors))


def _pollinations(prompt, out, width, height, seed, retries):
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
           + f"?width={width}&height={height}&seed={seed}&nologo=true")
    for _attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310 — HTTPS, хост задан константой
                data = r.read()
            if len(data) < 15000:
                raise RuntimeError("слишком маленький ответ")
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(data)
            print(f"Pollinations: {out} ({len(data)//1024} KB)", flush=True)
            return
        except urllib.error.HTTPError as e:
            if e.code == 402:
                wait = 60
                try:
                    wait = int(float(e.headers.get("Retry-After", 60)))
                except Exception:  # noqa: S110 — некорректный Retry-After → оставляем 60 секунд
                    pass
                time.sleep(wait + 2)
            else:
                time.sleep(8)
        except Exception:
            time.sleep(8)
    raise RuntimeError("лимит или сеть недоступны")


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
        genbg(pos[0], pos[1], int(opts.get("width", 886)), int(opts.get("height", 664)),
              int(opts.get("seed", 7)), do_upscale=opts.get("no-upscale") != "true",
              provider=opts.get("provider", "auto"), model=opts.get("model"))
    elif cmd == "upscale":
        upscale(pos[0], pos[1])
    else:
        print(f"неизвестная команда: {cmd}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
