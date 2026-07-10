"""Prescription flags."""

from __future__ import annotations

from typing import Any, Literal

FlagSeverity = Literal["informational", "advisory", "urgent"]

TEXT = {
    "rx_inactive": {
        "title": {"en": "Prescription no longer active", "de": "Rezept nicht mehr gültig"},
        "body": {
            "en": "This prescription was cancelled or stopped. Please speak with your doctor or pharmacist.",
            "de": "Dieses Rezept wurde storniert oder gestoppt. Sprechen Sie mit Arzt oder Apotheker.",
        },
    },
    "copay_required": {
        "title": {"en": "Co-payment may apply", "de": "Zuzahlung möglich"},
        "body": {
            "en": "You may need to pay a co-payment at the pharmacy. Worth confirming when you pick it up.",
            "de": "Möglicherweise fällt eine Zuzahlung an. Am besten in der Apotheke nachfragen.",
        },
    },
}


def _flag(severity: FlagSeverity, title: str, body: str, code: str) -> dict[str, str]:
    return {"severity": severity, "title": title, "body": body, "code": code}


def _msg(code: str, field: str, lang: str, fallback: str) -> str:
    return TEXT.get(code, {}).get(field, {}).get(lang) or fallback


def generate_prescription_flags(parsed: dict[str, Any], lang: str = "en") -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    status = (parsed.get("status") or "").lower()
    copay = str(parsed.get("copayment") or "")
    substitution = parsed.get("substitution_allowed")
    multiple = parsed.get("multiple_prescription")
    legal = str(parsed.get("legal_basis") or "")

    if status in ("cancelled", "stopped"):
        flags.append(_flag(
            "urgent",
            _msg("rx_inactive", "title", lang, "Prescription no longer active"),
            _msg("rx_inactive", "body", lang, "Speak with your doctor or pharmacist."),
            "rx_inactive",
        ))
    elif status == "completed":
        flags.append(_flag("informational", "Already dispensed", "If you need a refill, ask your doctor.", "rx_completed"))

    if copay == "1":
        flags.append(_flag(
            "advisory",
            _msg("copay_required", "title", lang, "Co-payment may apply"),
            _msg("copay_required", "body", lang, "Confirm amount at pharmacy."),
            "copay_required",
        ))

    if substitution is False or str(substitution).lower() == "false":
        flags.append(_flag("informational", "No generic substitute", "Pharmacy should not switch without checking.", "no_substitution"))

    if multiple is True or str(multiple).lower() == "true":
        flags.append(_flag("informational", "Repeat prescription", "Check instalment number and valid period.", "repeat_rx"))

    if legal == "02":
        flags.append(_flag("informational", "Self-pay", "Statutory insurance may not cover cost.", "self_pay"))

    if not parsed.get("medication_name") and not parsed.get("medications"):
        flags.append(_flag("advisory", "Medication incomplete", "Verify details with your pharmacist.", "medication_missing"))

    return flags
