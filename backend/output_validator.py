"""Validate patient-facing text — calm language, no diagnostic claims."""

from __future__ import annotations

import re
from typing import Any

ALARMING_PATTERNS = [
    r"\bwarning\b",
    r"\bdanger\b",
    r"\bemergency\b",
    r"\bcritical\b",
    r"\bfatal\b",
    r"\bimmediately stop\b",
    r"\byou have [a-z]+ disease\b",
    r"\byou are diagnosed\b",
]

REPLACEMENTS = {
    r"\bwarning\b": "please note",
    r"\bdangerous\b": "worth checking",
    r"\bcritical\b": "important",
}


def sanitize_text(text: str) -> str:
    if not text:
        return text
    out = text
    for pattern, replacement in REPLACEMENTS.items():
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


def validate_flags(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validated = []
    for flag in flags:
        validated.append(
            {
                **flag,
                "title": sanitize_text(flag.get("title", "")),
                "body": sanitize_text(flag.get("body", "")),
            }
        )
    return validated


def validate_humanized(humanized: dict[str, Any]) -> dict[str, Any]:
    summary = humanized.get("patient_summary")
    if summary:
        humanized = {**humanized, "patient_summary": sanitize_text(summary)}
    sections = humanized.get("sections") or {}
    clean_sections: dict[str, Any] = {}
    for key, section in sections.items():
        items = section.get("items") or {}
        clean_sections[key] = {
            **section,
            "title": sanitize_text(section.get("title", "")),
            "items": {k: sanitize_text(v) if isinstance(v, str) else v for k, v in items.items()},
        }
    return {**humanized, "sections": clean_sections}
