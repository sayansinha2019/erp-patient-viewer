"""Convert parsed FHIR data into plain-language summaries for patients."""

from __future__ import annotations

from typing import Any

from .code_maps import (
    COPAYMENT_STATUS,
    DOSAGE_FORM,
    FIELD_LABELS,
    FORM_TYPE,
    INSURANCE_TYPE,
    LEGAL_BASIS,
    MEDICATION_CATEGORY,
    PRESCRIPTION_STATUS,
)


def _map_value(field: str, raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    raw_str = str(raw)
    maps = {
        "legal_basis": LEGAL_BASIS,
        "form_type": FORM_TYPE,
        "copayment": COPAYMENT_STATUS,
        "dosage_form": DOSAGE_FORM,
        "insurance_type": INSURANCE_TYPE,
        "status": PRESCRIPTION_STATUS,
    }
    lookup = maps.get(field, {})
    return lookup.get(raw_str, raw_str)


def _bool_label(value: Any) -> str | None:
    if value is None:
        return None
    if str(value).lower() in ("true", "1"):
        return "Yes"
    if str(value).lower() in ("false", "0"):
        return "No"
    return str(value)


def humanize(parsed: dict[str, Any]) -> dict[str, Any]:
    """Return sections with English labels and humanized values (base layer before translation)."""
    fields: dict[str, str] = {}

    for key, label in FIELD_LABELS.items():
        raw = parsed.get(key)
        if key in ("substitution_allowed", "multiple_prescription"):
            value = _bool_label(raw)
        elif key in ("legal_basis", "form_type", "copayment", "dosage_form", "insurance_type", "status"):
            value = _map_value(key, raw)
        else:
            value = str(raw) if raw is not None else None
        if value:
            fields[label] = value

    if parsed.get("prescriber_specialty"):
        fields["Medical specialty"] = parsed["prescriber_specialty"]

    sections = {
        "summary": {
            "title": "Your e-prescription at a glance",
            "items": {
                k: v
                for k, v in fields.items()
                if k
                in {
                    FIELD_LABELS["prescription_id"],
                    FIELD_LABELS["document_title"],
                    FIELD_LABELS["prescription_date"],
                    FIELD_LABELS["status"],
                    FIELD_LABELS["medication_name"],
                    FIELD_LABELS["quantity"],
                }
            },
        },
        "patient": {
            "title": "About you",
            "items": {
                k: v
                for k, v in fields.items()
                if k
                in {
                    FIELD_LABELS["patient_name"],
                    FIELD_LABELS["patient_birth_date"],
                    FIELD_LABELS["patient_address"],
                    FIELD_LABELS["insurance_id"],
                    FIELD_LABELS["insurance_fund"],
                    FIELD_LABELS["insurance_type"],
                }
            },
        },
        "prescriber": {
            "title": "Prescribing doctor & practice",
            "items": {
                k: v
                for k, v in fields.items()
                if k
                in {
                    FIELD_LABELS["prescriber_name"],
                    "Medical specialty",
                    FIELD_LABELS["practice_name"],
                    FIELD_LABELS["practice_address"],
                    FIELD_LABELS["practice_phone"],
                }
            },
        },
        "medication": {
            "title": "Medication details",
            "items": {
                k: v
                for k, v in fields.items()
                if k
                in {
                    FIELD_LABELS["medication_name"],
                    FIELD_LABELS["pzn"],
                    FIELD_LABELS["dosage_form"],
                    FIELD_LABELS["quantity"],
                    FIELD_LABELS["substitution_allowed"],
                    FIELD_LABELS["copayment"],
                    FIELD_LABELS["multiple_prescription"],
                    FIELD_LABELS["multiple_prescription_number"],
                    FIELD_LABELS["multiple_prescription_period"],
                }
            },
        },
        "technical": {
            "title": "Technical details (for reference)",
            "items": {
                k: v
                for k, v in fields.items()
                if k
                in {
                    FIELD_LABELS["legal_basis"],
                    FIELD_LABELS["form_type"],
                }
            },
        },
    }

    pipeline_status = {
        "parse_ok": bool(parsed.get("prescription_id") or parsed.get("bundle_id")),
        "has_patient": bool(parsed.get("patient_name")),
        "has_medication": bool(parsed.get("medication_name")),
        "has_prescriber": bool(parsed.get("prescriber_name")),
        "resource_count": parsed.get("resource_count", 0),
    }

    return {
        "sections": sections,
        "all_fields": fields,
        "pipeline_status": pipeline_status,
        "source_language": "en",
    }


def build_explanation_cards(parsed: dict[str, Any], humanized: dict[str, Any]) -> list[dict[str, Any]]:
    """Klarify explanation cards: clinical label + original text + plain-language body."""
    cards: list[dict[str, Any]] = []
    sections = humanized.get("sections") or {}

    med_clinical = " · ".join(
        p
        for p in [
            parsed.get("medication_name"),
            parsed.get("dosage_form"),
            parsed.get("quantity"),
        ]
        if p
    )
    med_items = sections.get("medication", {}).get("items") or {}
    med_body = humanized.get("patient_summary") or ". ".join(med_items.values()) if med_items else None
    if med_clinical or med_body:
        cards.append(
            {
                "label": "MEDICATION",
                "clinical_text": med_clinical or parsed.get("medication_name") or "—",
                "explanation": med_body or "Your prescribed medicine is listed above.",
                "section_key": "medication",
            }
        )

    summary_items = sections.get("summary", {}).get("items") or {}
    if summary_items:
        cards.append(
            {
                "label": "PRESCRIPTION",
                "clinical_text": parsed.get("prescription_id") or parsed.get("document_title") or "E-Rezept",
                "explanation": ". ".join(f"{k}: {v}" for k, v in summary_items.items()),
                "section_key": "summary",
            }
        )

    patient_items = sections.get("patient", {}).get("items") or {}
    if patient_items:
        cards.append(
            {
                "label": "PATIENT & INSURANCE",
                "clinical_text": parsed.get("patient_name") or "Patient details",
                "explanation": ". ".join(f"{k}: {v}" for k, v in patient_items.items()),
                "section_key": "patient",
            }
        )

    prescriber_items = sections.get("prescriber", {}).get("items") or {}
    if prescriber_items:
        cards.append(
            {
                "label": "PRESCRIBER",
                "clinical_text": parsed.get("prescriber_name") or "Prescribing doctor",
                "explanation": ". ".join(f"{k}: {v}" for k, v in prescriber_items.items()),
                "section_key": "prescriber",
            }
        )

    return cards
