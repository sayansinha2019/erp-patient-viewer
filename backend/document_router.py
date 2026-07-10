"""Route FHIR bundles and extracted text to document-type parsers."""

from __future__ import annotations

import json
import re
from typing import Any

from .fhir_parser import parse_fhir
from .parsers.discharge import parse_discharge
from .parsers.doctor_letter import parse_doctor_letter
from .parsers.lab import parse_lab
from .parsers.prescription import parse_prescription_bundle
from .parsers.referral import parse_referral


def detect_document_type(content: str | bytes, filename: str | None = None) -> str:
    text = content.decode() if isinstance(content, bytes) else content
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            data = json.loads(text)
            return _detect_from_bundle(data)
        except json.JSONDecodeError:
            pass
    if "<Bundle" in text or "MedicationRequest" in text:
        if "MedicationRequest" in text and "DiagnosticReport" not in text:
            return "prescription"
        if "DiagnosticReport" in text or "Observation" in text:
            return "lab_result"
        if "ServiceRequest" in text:
            return "referral"
        if "Composition" in text:
            if "Entlass" in text or "discharge" in text.lower():
                return "discharge"
            return "doctor_letter"
    if filename and filename.lower().endswith(".pdf"):
        return "pdf"
    return "prescription"


def _detect_from_bundle(data: dict) -> str:
    types = set()
    composition = None
    for entry in data.get("entry", []):
        rtype = entry.get("resource", {}).get("resourceType")
        if rtype:
            types.add(rtype)
        if rtype == "Composition":
            composition = entry.get("resource")

    if composition:
        title = (composition.get("title") or "").lower()
        doc_type = ((composition.get("type", {}).get("coding") or [{}])[0]).get("code", "")
        if "discharge" in title or "entlass" in title or doc_type in ("18842-5", "34105-7"):
            return "discharge"
        return "doctor_letter"

    if "DiagnosticReport" in types or ("Observation" in types and "MedicationRequest" not in types):
        return "lab_result"
    if "ServiceRequest" in types:
        return "referral"
    if "MedicationRequest" in types:
        return "prescription"
    return "prescription"


def parse_document(content: str | bytes, filename: str | None = None) -> dict[str, Any]:
    doc_type = detect_document_type(content, filename)
    parsers = {
        "prescription": parse_prescription_bundle,
        "lab_result": parse_lab,
        "discharge": parse_discharge,
        "referral": parse_referral,
        "doctor_letter": parse_doctor_letter,
    }
    parser = parsers.get(doc_type, parse_prescription_bundle)
    parsed = parser(content, filename=filename)
    parsed["document_type"] = doc_type
    return parsed


def extract_codes_from_text(text: str) -> dict[str, list[str]]:
    """PDF fallback — pattern match ICD-10, LOINC, ATC from plain text."""
    icd = re.findall(r"\b[A-Z][0-9]{2}(?:\.[0-9]{1,2})?\b", text)
    loinc = re.findall(r"\b\d{4,5}-\d\b", text)
    atc = re.findall(r"\b[A-Z][0-9]{2}[A-Z]{2}[0-9]{2}\b", text)
    return {
        "diagnosis_codes": list(dict.fromkeys(icd))[:20],
        "loinc_codes": list(dict.fromkeys(loinc))[:20],
        "atc_codes": list(dict.fromkeys(atc))[:20],
    }
