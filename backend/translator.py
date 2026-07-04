"""Translate humanized e-prescription summaries to the user's language."""

from __future__ import annotations

import os
from typing import Any

from .gemini_client import enhance_and_translate, is_available
from .logging_config import get_logger
from .languages import SUPPORTED_LANGUAGES
from .offline_translator import translate_offline
from .translation_cache import get_cached_bundle, make_bundle_cache_id, set_cached_bundle


def _translation_mode() -> str:
    return os.getenv("TRANSLATION_MODE", "auto").lower()


def _translate_text_fallback(text: str, target: str, source: str = "en") -> str:
    if not text or target == source:
        return text
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source=source, target=target).translate(text)
    except Exception:
        return text


def _fallback_translate(humanized: dict[str, Any], target_lang: str) -> dict[str, Any]:
    sections = humanized["sections"]
    translated_sections: dict[str, Any] = {}

    for section_key, section in sections.items():
        translated_items = {}
        for label, value in section["items"].items():
            t_label = _translate_text_fallback(label, target_lang)
            t_value = _translate_text_fallback(value, target_lang) if value else value
            translated_items[t_label] = t_value
        translated_sections[section_key] = {
            "title": _translate_text_fallback(section["title"], target_lang),
            "items": translated_items,
        }

    return {
        **humanized,
        "sections": translated_sections,
        "target_language": target_lang,
        "translated": target_lang != "en",
        "translation_provider": "online_fallback",
        "patient_summary": None,
        "gemini_available": is_available(),
    }


def translate_humanized(
    humanized: dict[str, Any],
    target_lang: str,
    parsed: dict[str, Any] | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    log = get_logger("translator")
    lang_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)
    effective_mode = (mode or _translation_mode()).lower()
    log.debug("translate lang=%s mode=%s", target_lang, effective_mode)

    cache_id = make_bundle_cache_id(parsed or {}, target_lang) if parsed else None
    if effective_mode in ("auto", "offline") and cache_id:
        cached = get_cached_bundle(cache_id)
        if cached:
            return {**humanized, **cached, "translation_provider": "cache", "from_cache": True}

    if effective_mode == "offline":
        result = translate_offline(humanized, target_lang)
        return {**result, "gemini_available": is_available()}

    if effective_mode in ("auto", "gemini") and parsed is not None and is_available():
        gemini_result = enhance_and_translate(humanized, parsed, target_lang, lang_name)
        if gemini_result:
            output = {
                **humanized,
                "sections": gemini_result["sections"],
                "target_language": target_lang,
                "translated": target_lang != "en",
                "translation_provider": "gemini",
                "patient_summary": gemini_result.get("patient_summary"),
                "gemini_available": True,
            }
            if cache_id:
                set_cached_bundle(
                    cache_id,
                    {
                        "sections": output["sections"],
                        "target_language": target_lang,
                        "translated": output["translated"],
                        "patient_summary": output.get("patient_summary"),
                    },
                )
            return output

    if effective_mode == "offline" or effective_mode == "auto":
        offline_result = translate_offline(humanized, target_lang)
        if target_lang == "en" or offline_result.get("sections"):
            if target_lang != "en":
                return {**offline_result, "gemini_available": is_available()}

    if target_lang == "en":
        return {
            **humanized,
            "target_language": "en",
            "translated": False,
            "translation_provider": "none",
            "patient_summary": None,
            "gemini_available": is_available(),
        }

    if effective_mode == "online" or effective_mode == "auto":
        return _fallback_translate(humanized, target_lang)

    return translate_offline(humanized, target_lang)
