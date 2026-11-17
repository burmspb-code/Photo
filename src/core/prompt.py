"""Подготовка промпта генерации: перевод русского текста и обязательная фраза.

Русские промпты переводятся через публичный endpoint Google Translate — ключ
не нужен. Если сервис недоступен, промпт уходит в провайдера как есть (в лог
GUI при этом попадает предупреждение). Упоминание разрешения («в 2К», «4k»)
удаляется: размером управляет пресет ``bg/size``, а не слова в промпте.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from src.core import settings  # noqa: F401 — применение IPv4-патча при импорте

PROMPT_BASE = "realistic photo, no people, no text"
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
# «в 2К», «in 4k», «2K», «разрешение 2К» — всё это не должно уходить в модель.
_RESOLUTION = re.compile(
    r"\b(?:в|in|at|разрешение|resolution)\s*[: -]?\s*\d\s*[kKКк]\b|\b\d\s*[kKКк]\b",
    re.IGNORECASE,
)


def has_cyrillic(text: str) -> bool:
    """Есть ли в тексте кириллица — по этому признаку включаем перевод."""
    return bool(_CYRILLIC.search(str(text or "")))


def strip_resolution(text: str) -> str:
    """Убрать из промпта упоминания разрешения и лишние разделители."""
    text = _RESOLUTION.sub("", str(text or ""))
    text = re.sub(r"\s*[-–—]\s*", ", ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,;:])", r"\1", text)
    return text.strip(" ,;:-–—")


def translate_to_english(text: str, timeout: float = 15) -> str:
    """Перевести русский промпт. При любой ошибке вернуть исходный текст."""
    text = str(text or "").strip()
    if not has_cyrillic(text):
        return text
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode({
        "client": "gtx", "sl": "ru", "tl": "en", "dt": "t", "q": text,
    })
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 — HTTPS
            payload = json.loads(response.read().decode("utf-8"))
        translated = "".join(
            part[0] for part in payload[0] if part and part[0]
        )
        return translated.strip() or text
    except Exception:  # сеть или формат ответа: промпт уйдёт как есть
        return text


def prepare_prompt(text) -> str:
    """Перевести при необходимости, убрать «2К» и добавить обязательную фразу."""
    value = strip_resolution(str(text or "").strip())
    value = strip_resolution(translate_to_english(value))
    # Дописываем только недостающие части: «take a realistic photo» уже содержит
    # «realistic», и полная фраза давала бы дубль.
    lower = value.lower()
    missing = [
        part for part in ("realistic", "no people", "no text")
        if part not in lower
    ]
    if missing:
        addition = "realistic photo" if "realistic" in missing else ""
        rest = [p for p in missing if p != "realistic"]
        parts = ([addition] if addition else []) + rest
        value = f"{value}, {', '.join(parts)}" if value else ", ".join(parts)
    return value
