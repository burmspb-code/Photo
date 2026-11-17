"""Чтение/запись изображений, CV-хелперы и анализ снимка."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


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
