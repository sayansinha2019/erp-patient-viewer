"""Parse FHIR ServiceRequest — referral (Überweisung)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

FHIR_NS = {"f": "http://hl7.org/fhir"}


def _parse_json(data: dict) -> dict[str, Any]:
    sr = next(
        (e["resource"] for e in data.get("entry", []) if e.get("resource", {}).get("resourceType") == "ServiceRequest"),
        {},
    )
    code = sr.get("code", {})
    reason = sr.get("reasonCode", [{}])[0] if sr.get("reasonCode") else {}
    return {
        "document_title": "Überweisung",
        "specialist": code.get("text") or ((code.get("coding") or [{}])[0]).get("display"),
        "urgency": sr.get("priority"),
        "clinical_question": sr.get("note", [{}])[0].get("text") if sr.get("note") else None,
        "diagnosis_codes": [((reason.get("coding") or [{}])[0]).get("code")] if reason else [],
        "reason_text": reason.get("text"),
        "medications": [],
        "observations": [],
    }


def _parse_xml(content: str) -> dict[str, Any]:
    root = ET.fromstring(content)
    specialist = None
    for entry in root.findall("f:entry", FHIR_NS):
        sr = entry.find(".//f:ServiceRequest", FHIR_NS)
        if sr is not None:
            code = sr.find("f:code/f:text", FHIR_NS)
            specialist = code.get("value") if code is not None else "Specialist referral"
    return {
        "document_title": "Überweisung",
        "specialist": specialist,
        "diagnosis_codes": [],
        "medications": [],
        "observations": [],
    }


def parse_referral(content: str | bytes, filename: str | None = None) -> dict[str, Any]:
    text = content.decode() if isinstance(content, bytes) else content
    if text.lstrip().startswith("{"):
        return _parse_json(json.loads(text))
    return _parse_xml(text)
