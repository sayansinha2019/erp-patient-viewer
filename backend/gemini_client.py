"""Google Gemini integration for translation and patient-friendly explanations."""

from __future__ import annotations

import json
import os
import re
from typing import Any

_CLIENT: Any = None
_DEFAULT_MODEL = "gemini-2.5-flash"


def _get_client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai

        _CLIENT = genai.Client(api_key=api_key)
        return _CLIENT
    except Exception:
        return None


def is_available() -> bool:
    return _get_client() is not None


def _model_name() -> str:
    return os.getenv("GEMINI_MODEL", _DEFAULT_MODEL)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _generate(prompt: str) -> str | None:
    return _generate_text(prompt, json_mode=True)


def _generate_text(prompt: str, json_mode: bool = False) -> str | None:
    client = _get_client()
    if client is None:
        return None
    config: dict[str, Any] = {"temperature": 0.3}
    if json_mode:
        config["response_mime_type"] = "application/json"
    try:
        response = client.models.generate_content(
            model=_model_name(),
            contents=prompt,
            config=config,
        )
        return response.text
    except Exception:
        try:
            response = client.models.generate_content(
                model=_model_name(),
                contents=prompt,
            )
            return response.text
        except Exception:
            return None


def enhance_and_translate(
    humanized: dict[str, Any],
    parsed: dict[str, Any],
    target_lang: str,
    lang_name: str,
) -> dict[str, Any] | None:
    """
    Use Gemini to translate section content and add a plain-language patient summary.
    Returns None if Gemini is unavailable or fails.
    """
    sections_json = json.dumps(humanized["sections"], ensure_ascii=False, indent=2)
    parsed_json = json.dumps(parsed, ensure_ascii=False, indent=2)

    if target_lang == "en":
        prompt = f"""You are a healthcare communication expert helping patients understand German e-prescriptions (E-Rezept).

Given structured prescription data and section labels in English, produce:
1. Clearer, patient-friendly section titles and field labels (still in English).
2. Values rewritten in simple language a non-medical person understands. Keep exact: drug names, PZN codes, prescription IDs, dates, addresses, phone numbers, insurance numbers, doctor names.
3. A short "patient_summary" (2-4 sentences) explaining what this prescription is and what the patient should do next.

Raw FHIR-derived data:
{parsed_json}

Current sections JSON:
{sections_json}

Return ONLY valid JSON with this exact shape:
{{
  "sections": {{ "summary": {{ "title": "...", "items": {{ "Label": "value" }} }}, ... }},
  "patient_summary": "..."
}}

Keep the same section keys: summary, patient, prescriber, medication, technical.
Omit empty items from sections."""
    else:
        prompt = f"""You are a healthcare communication expert helping patients understand German e-prescriptions (E-Rezept).

Translate and explain the prescription for a patient who speaks {lang_name} (language code: {target_lang}).

Rules:
- Translate all section titles and field labels into {lang_name}.
- Translate explanatory text into {lang_name}.
- Do NOT translate: medication product names, PZN numbers, prescription IDs, dates, postal addresses, phone numbers, insurance card numbers, personal names, organization names unless they have a well-known translation.
- Explain medical/insurance terms (e.g. co-payment, statutory insurance) in simple {lang_name}.
- Add a "patient_summary" field: 2-4 sentences in {lang_name} explaining what this prescription is and practical next steps (e.g. take to pharmacy).

Raw FHIR-derived data:
{parsed_json}

English sections to translate:
{sections_json}

Return ONLY valid JSON:
{{
  "sections": {{ "summary": {{ "title": "...", "items": {{ "Label": "value" }} }}, ... }},
  "patient_summary": "..."
}}

Keep section keys: summary, patient, prescriber, medication, technical."""

    raw = _generate(prompt)
    if not raw:
        return None

    try:
        data = _extract_json(raw)
        if "sections" not in data:
            return None
        return {
            "sections": data["sections"],
            "patient_summary": data.get("patient_summary", ""),
            "translation_provider": "gemini",
        }
    except (json.JSONDecodeError, KeyError):
        return None
