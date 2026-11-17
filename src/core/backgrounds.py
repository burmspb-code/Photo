"""Генерация фона: провайдеры API, выбор и апскейл результата."""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import cv2
import numpy as np

from src.core.image import _write
from src.core.settings import (
    CF_CREDS,
    ESR_MODEL,
    GOOGLE_KEY_FILE,
    GOOGLE_KEY_TXT,
    HF_TOKEN_TXT,
    STABILITY_KEY_TXT,
)
from src.core.upscale import upscale


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


def stability_key():
    key = (os.environ.get("STABILITY_API_KEY") or "").strip()
    if key:
        return key
    if STABILITY_KEY_TXT.exists():
        return STABILITY_KEY_TXT.read_text(encoding="utf-8").strip()
    return ""


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
