"""Google Gemini integration for translation and patient-friendly explanations."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .logging_config import get_logger

log = get_logger("gemini")
_CLIENT: Any = None
_DEFAULT_MODEL = "gemini-3-flash-preview"


def _service_account_info() -> dict[str, Any] | None:
    """Service account JSON from GCP_SERVICE_ACCOUNT_KEY (inline JSON) if set."""
    raw = (os.getenv("GCP_SERVICE_ACCOUNT_KEY") or "").strip()
    if not raw:
        return None
    try:
        info = json.loads(raw)
        return info if info.get("type") == "service_account" else None
    except json.JSONDecodeError:
        log.error("GCP_SERVICE_ACCOUNT_KEY is not valid JSON — ignoring it")
        return None


def _get_client():
    """
    Prefer Vertex AI (service account) when configured, else the Gemini API key.

    Vertex: GCP_SERVICE_ACCOUNT_KEY (inline JSON) or GOOGLE_APPLICATION_CREDENTIALS (file),
    plus GCP_PROJECT_ID and optional GCP_LOCATION (default "global").
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    try:
        from google import genai
    except Exception:
        log.exception("google-genai is not installed")
        return None

    info = _service_account_info()
    project = os.getenv("GCP_PROJECT_ID") or (info or {}).get("project_id")
    location = os.getenv("GCP_LOCATION", "global")
    use_adc = os.getenv("GEMINI_USE_VERTEX", "").lower() in ("1", "true", "yes")  # e.g. Cloud Run identity
    if project and (info or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or use_adc):
        try:
            creds = None
            if info:
                from google.oauth2 import service_account

                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            _CLIENT = genai.Client(vertexai=True, project=project, location=location, credentials=creds)
            log.info("Gemini via Vertex AI (project=%s, location=%s)", project, location)
            return _CLIENT
        except Exception:
            log.exception("Could not create Vertex AI client — falling back to API key")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        _CLIENT = genai.Client(api_key=api_key)
        return _CLIENT
    except Exception:
        log.exception("Could not create Gemini client")
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
    except Exception as first_exc:
        if _is_auth_error(first_exc) or "404" in str(first_exc):
            log.error("Gemini rejected the request (key or billing) — check GEMINI_API_KEY / AI Studio credits: %s", str(first_exc)[:200])
            return None
        try:
            response = client.models.generate_content(
                model=_model_name(),
                contents=prompt,
            )
            return response.text
        except Exception as exc:
            log.warning("Gemini request failed: %s", str(exc)[:300])
            return None


def _is_auth_error(exc: Exception) -> bool:
    text = str(exc)
    return any(
        marker in text
        for marker in ("401", "402", "403", "API key not valid", "PERMISSION_DENIED", "UNAUTHENTICATED", "credits are depleted")
    )


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
