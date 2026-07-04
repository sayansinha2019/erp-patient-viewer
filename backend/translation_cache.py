"""Disk cache for translations (enables offline reuse after first online translation)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "translations"


def _key(text: str, target_lang: str, kind: str = "text") -> str:
    digest = hashlib.sha256(f"{kind}:{target_lang}:{text}".encode()).hexdigest()
    return digest


def get_cached(text: str, target_lang: str, kind: str = "text") -> str | None:
    path = CACHE_DIR / f"{_key(text, target_lang, kind)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("translation")
    except (json.JSONDecodeError, OSError):
        return None


def set_cached(text: str, target_lang: str, translation: str, kind: str = "text") -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_key(text, target_lang, kind)}.json"
    path.write_text(
        json.dumps({"source": text, "target_lang": target_lang, "translation": translation}, ensure_ascii=False),
        encoding="utf-8",
    )


def get_cached_bundle(cache_id: str) -> dict[str, Any] | None:
    path = CACHE_DIR / f"bundle_{cache_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def set_cached_bundle(cache_id: str, data: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"bundle_{cache_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_bundle_cache_id(parsed: dict[str, Any], target_lang: str) -> str:
    raw = f"{parsed.get('prescription_id') or parsed.get('bundle_id')}:{target_lang}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
