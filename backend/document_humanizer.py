"""Humanize all document types into Klarify sections + explanation cards."""

from __future__ import annotations

from typing import Any

from .dictionaries.clinical_index import resolve_icd10, resolve_loinc
from .humanizer import build_explanation_cards, humanize


def humanize_document(parsed: dict[str, Any], doc_type: str) -> dict[str, Any]:
    if doc_type == "prescription":
        return humanize(parsed)

    sections: dict[str, Any] = {}
    if doc_type == "lab_result":
        items = {}
        for i, obs in enumerate(parsed.get("observations", []) or []):
            label = obs.get("display") or obs.get("loinc_code") or f"Test {i+1}"
            val = obs.get("value")
            unit = obs.get("unit") or ""
            items[label] = f"{val} {unit}".strip() if val is not None else "—"
        sections["results"] = {"title": "Your lab results", "items": items}
    elif doc_type == "discharge":
        items = {}
        for d in parsed.get("diagnoses", []) or []:
            code = d.get("code")
            desc = d.get("description") or resolve_icd10(code) or code
            items[f"Diagnosis {code}"] = desc
        for m in parsed.get("medications", []) or []:
            if m.get("name"):
                items[m["name"]] = "Prescribed at discharge"
        sections["summary"] = {"title": "Discharge summary", "items": items}
    elif doc_type == "referral":
        sections["summary"] = {
            "title": "Referral details",
            "items": {
                k: v for k, v in {
                    "Specialist": parsed.get("specialist"),
                    "Reason": parsed.get("reason_text") or parsed.get("clinical_question"),
                    "Urgency": parsed.get("urgency"),
                }.items() if v
            },
        }
    else:
        sections["summary"] = {
            "title": parsed.get("document_title") or "Document",
            "items": {"Instructions": (parsed.get("patient_instructions") or parsed.get("clinical_narrative") or "")[:500]},
        }

    return {
        "sections": sections,
        "all_fields": {},
        "pipeline_status": {"parse_ok": True, "document_type": doc_type},
        "source_language": "en",
    }


def build_cards_for_document(parsed: dict[str, Any], humanized: dict[str, Any], doc_type: str) -> list[dict[str, Any]]:
    if doc_type == "prescription":
        return build_explanation_cards(parsed, humanized)

    cards = []
    if humanized.get("patient_summary"):
        cards.append({
            "label": "SUMMARY",
            "clinical_text": parsed.get("document_title", ""),
            "explanation": humanized["patient_summary"],
            "section_key": "summary",
        })

    if doc_type == "lab_result":
        for obs in parsed.get("observations", []) or []:
            loinc = obs.get("loinc_code")
            meta = resolve_loinc(loinc) if loinc else {}
            clinical = f"{meta.get('name') or obs.get('display') or loinc}: {obs.get('value')} {obs.get('unit') or ''}".strip()
            cards.append({
                "label": "LAB RESULT",
                "clinical_text": clinical,
                "explanation": f"This test measures {meta.get('component', 'a blood value')}. Discuss with your doctor if unsure.",
                "section_key": "lab",
            })
    elif doc_type == "discharge":
        for d in parsed.get("diagnoses", []) or []:
            cards.append({
                "label": "DIAGNOSIS",
                "clinical_text": d.get("code", ""),
                "explanation": d.get("description") or resolve_icd10(d.get("code")) or "See your discharge letter.",
                "section_key": "diagnosis",
            })
    else:
        for section in (humanized.get("sections") or {}).values():
            if section.get("items"):
                cards.append({
                    "label": section.get("title", "SECTION").upper()[:20],
                    "clinical_text": parsed.get("document_title", ""),
                    "explanation": ". ".join(f"{k}: {v}" for k, v in section["items"].items()),
                    "section_key": "summary",
                })
    return cards
