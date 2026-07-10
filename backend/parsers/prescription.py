"""Prescription parser — wraps existing FHIR e-Rx logic."""

from __future__ import annotations

from typing import Any

from ..fhir_parser import parse_fhir


def parse_prescription_bundle(content: str | bytes, filename: str | None = None) -> dict[str, Any]:
    parsed = parse_fhir(content, filename=filename)
    meds = []
    if parsed.get("medication_name"):
        meds.append({"name": parsed.get("medication_name"), "atc_code": parsed.get("atc_code"), "pzn": parsed.get("pzn")})
    parsed["medications"] = meds
    parsed["diagnosis_codes"] = parsed.get("diagnosis_codes") or []
    return parsed
