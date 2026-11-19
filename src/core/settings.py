"""Пути проекта, модели и ключи API."""
from __future__ import annotations

import os
import socket
from pathlib import Path

# На этой сети IPv6 часто зависает — принудительно предпочитаем IPv4.
# Патч применяется при импорте этого модуля, то есть до импорта rembg и сетевых вызовов.
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

HERE = Path(__file__).resolve().parent          # src\core
PROJECT_ROOT = HERE.parent.parent               # корень проекта
RUNTIME_DIR = Path(
    os.environ.get("PHOTO_RUNTIME_DIR")
    or (Path(os.environ.get("LOCALAPPDATA", "")) / "rembg-env")
)                                               # рабочее окружение и ключи


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
ESR_MODEL = _model_path("realesr-general-x4v3.onnx")   # апскейл ×4
EDSR_X2_MODEL = _model_path("edsr-x2.onnx")            # апскейл ×2

UPSCALE_FACTORS = (2, 4)


def normalize_factor(value) -> int:
    """Кратность апскейла: 2 или 4; всё остальное приводится к 2."""
    try:
        factor = int(value)
    except (TypeError, ValueError):
        return 2
    return factor if factor in UPSCALE_FACTORS else 2

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
