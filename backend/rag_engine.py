"""RAG translation engine — retrieve clinical context then generate explanation."""

from __future__ import annotations

import json
from typing import Any

from .dictionaries.clinical_index import resolve_atc, resolve_icd10, resolve_loinc, semantic_search
from .gemini_client import _generate_text, is_available
from .logging_config import get_logger
from .output_validator import sanitize_text

log = get_logger("rag")

PROMPTS = {
    "prescription": """Explain this e-prescription to a patient in {lang_name} ({lang}).
Use calm, plain language. Do not diagnose. End with practical next steps.
Retrieved clinical context:
{context}

Structured data:
{data}

Return JSON: {{"patient_summary": "...", "sections": {{...}} optional}}""",
    "lab_result": """Explain these lab results to a patient in {lang_name} ({lang}).
For each result say what was measured, whether it is in/out of normal range, and what to discuss with a doctor.
Never use alarming language. Retrieved context:
{context}

Lab data:
{data}

Return JSON: {{"patient_summary": "...", "observations": [{{"name","value","explanation"}}]}}""",
    "discharge": """Explain this hospital discharge letter in {lang_name} ({lang}).
Cover diagnosis, medications, and follow-up instructions plainly.
{context}

Data:
{data}

Return JSON: {{"patient_summary": "...", "diagnoses": [], "medications": [], "follow_up": ""}}""",
    "referral": """Explain this referral letter in {lang_name} ({lang}).
{context}

Data:
{data}

Return JSON: {{"patient_summary": "...", "specialist": "", "reason": ""}}""",
    "doctor_letter": """Explain this doctor letter in {lang_name} ({lang}).
{context}

Data:
{data}

Return JSON: {{"patient_summary": "...", "instructions": ""}}""",
}


def _build_context(parsed: dict[str, Any], doc_type: str) -> str:
    parts = []
    for code in parsed.get("diagnosis_codes", []) or []:
        desc = resolve_icd10(code)
        if desc:
            parts.append(f"ICD-10 {code}: {desc}")
    for obs in parsed.get("observations", []) or []:
        loinc = obs.get("loinc_code")
        meta = resolve_loinc(loinc) if loinc else None
        if meta:
            parts.append(f"LOINC {loinc}: {meta.get('name')}")
    for med in parsed.get("medications", []) or []:
        atc = med.get("atc_code")
        meta = resolve_atc(atc) if atc else None
        if meta:
            parts.append(f"ATC {atc}: {meta.get('name')}")
    queries = [parsed.get("medication_name"), parsed.get("document_title"), parsed.get("clinical_narrative")]
    for med in parsed.get("medications", []) or []:
        if not med.get("atc_code"):
            queries.append(med.get("name"))
    for q in queries:
        if q:
            parts.extend(semantic_search(str(q)[:300], n=2))
    deduped = list(dict.fromkeys(str(p) for p in parts))
    return "\n".join(deduped[:12]) or "(no additional context)"


def generate_explanation(
    parsed: dict[str, Any],
    doc_type: str,
    lang: str,
    lang_name: str,
) -> dict[str, Any] | None:
    if not is_available():
        return None

    template = PROMPTS.get(doc_type, PROMPTS["prescription"])
    prompt = template.format(
        lang=lang,
        lang_name=lang_name,
        context=_build_context(parsed, doc_type),
        data=json.dumps(parsed, ensure_ascii=False, indent=2),
    )
    raw = _generate_text(prompt, json_mode=True)
    if not raw:
        return None
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        data = json.loads(cleaned)
        if data.get("patient_summary"):
            data["patient_summary"] = sanitize_text(data["patient_summary"])
        data["rag_provider"] = "gemini+chromadb"
        return data
    except json.JSONDecodeError:
        log.warning("RAG JSON parse failed for %s", doc_type)
        return {"patient_summary": sanitize_text(raw[:1500]), "rag_provider": "gemini_fallback"}
