"""Offline translation using pre-built UI labels and disk cache."""

from __future__ import annotations

from typing import Any

from .languages import EN_LABEL_TO_KEY, SECTION_KEY_MAP, UI_LABELS
from .translation_cache import get_cached, set_cached


def _label_for_lang(en_label: str, lang: str) -> str:
    key = EN_LABEL_TO_KEY.get(en_label)
    if key and lang in UI_LABELS and key in UI_LABELS[lang]:
        return UI_LABELS[lang][key]
    return en_label


def _section_title_for_lang(en_title: str, lang: str) -> str:
    key = SECTION_KEY_MAP.get(en_title)
    if key and lang in UI_LABELS and key in UI_LABELS[lang]:
        return UI_LABELS[lang][key]
    return en_title


def _translate_value_cached(value: str, lang: str) -> str:
    if not value or lang == "en":
        return value
    cached = get_cached(value, lang, kind="value")
    if cached:
        return cached
    return value


def translate_offline(humanized: dict[str, Any], target_lang: str) -> dict[str, Any]:
    """Relabel sections offline; translate values only from cache."""
    if target_lang == "en":
        return {
            **humanized,
            "target_language": "en",
            "translated": False,
            "translation_provider": "offline",
            "patient_summary": humanized.get("patient_summary"),
        }

    sections = humanized["sections"]
    translated_sections: dict[str, Any] = {}

    for section_key, section in sections.items():
        offline_section_key = f"section.{section_key}"
        title = section["title"]
        if target_lang in UI_LABELS and offline_section_key in UI_LABELS[target_lang]:
            new_title = UI_LABELS[target_lang][offline_section_key]
        else:
            new_title = _section_title_for_lang(title, target_lang)

        items = {}
        for label, value in section["items"].items():
            new_label = _label_for_lang(label, target_lang)
            new_value = _translate_value_cached(str(value), target_lang) if value else value
            items[new_label] = new_value

        translated_sections[section_key] = {"title": new_title, "items": items}

    summary_key = f"bundle_summary_{target_lang}"
    patient_summary = get_cached(
        humanized.get("patient_summary") or humanized.get("all_fields", {}).get("Prescription ID", ""),
        target_lang,
        kind="summary",
    )

    return {
        **humanized,
        "sections": translated_sections,
        "target_language": target_lang,
        "translated": True,
        "translation_provider": "offline",
        "patient_summary": patient_summary,
        "offline_note": "Labels translated offline. Values use cache where available.",
    }


def cache_gemini_result(humanized: dict[str, Any], target_lang: str) -> None:
    """Persist Gemini output so offline mode can reuse it."""
    for section in humanized.get("sections", {}).values():
        for label, value in section.get("items", {}).items():
            if value:
                set_cached(str(value), target_lang, str(value), kind="value")
    summary = humanized.get("patient_summary")
    if summary:
        pid = humanized.get("all_fields", {}).get("Prescription ID", "summary")
        set_cached(pid, target_lang, summary, kind="summary")
