"""Layer 2 — unified clinical flagging."""

from __future__ import annotations

from typing import Any, Literal

from .drugs import check_drug_interactions
from .follow_up import detect_follow_up_flags
from .lab import generate_lab_flags
from .prescription import generate_prescription_flags

FlagSeverity = Literal["informational", "advisory", "urgent"]


def generate_all_flags(parsed: dict[str, Any], doc_type: str, lang: str = "en") -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    if doc_type == "prescription":
        flags.extend(generate_prescription_flags(parsed, lang=lang))
        flags.extend(check_drug_interactions(parsed, lang=lang))
    elif doc_type == "lab_result":
        flags.extend(generate_lab_flags(parsed, lang=lang))
    elif doc_type in ("discharge", "doctor_letter"):
        flags.extend(detect_follow_up_flags(parsed, lang=lang))
        if doc_type == "discharge":
            flags.extend(check_drug_interactions(parsed, lang=lang))
    elif doc_type == "referral":
        if parsed.get("urgency") in ("urgent", "asap"):
            flags.append({
                "severity": "advisory",
                "title": _t("urgent_referral_title", lang),
                "body": _t("urgent_referral_body", lang),
                "code": "referral_urgent",
            })
    return flags


def _t(key: str, lang: str) -> str:
    from .i18n import translate_flag

    return translate_flag(key, lang)
