"""Parse FHIR Composition — doctor letter (Arztbrief)."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any

FHIR_NS = {"f": "http://hl7.org/fhir"}


def _parse_json(data: dict) -> dict[str, Any]:
    composition = next(
        (e["resource"] for e in data.get("entry", []) if e.get("resource", {}).get("resourceType") == "Composition"),
        {},
    )
    narrative = ""
    for section in composition.get("section", []):
        text = section.get("text", {}).get("div", "")
        narrative += " " + re.sub(r"<[^>]+>", " ", text)
    return {
        "document_title": composition.get("title") or "Arztbrief",
        "letter_date": composition.get("date"),
        "clinical_narrative": narrative.strip()[:4000],
        "patient_instructions": narrative.strip()[:2000],
        "diagnosis_codes": [],
        "medications": [],
        "observations": [],
    }


def _parse_xml(content: str) -> dict[str, Any]:
    root = ET.fromstring(content)
    title = "Arztbrief"
    narrative = ""
    for entry in root.findall("f:entry", FHIR_NS):
        comp = entry.find(".//f:Composition", FHIR_NS)
        if comp is not None:
            t = comp.find("f:title", FHIR_NS)
            if t is not None:
                title = t.get("value", title)
            for div in comp.findall(".//f:div", FHIR_NS):
                if div.text:
                    narrative += " " + div.text
    return {
        "document_title": title,
        "clinical_narrative": narrative.strip(),
        "patient_instructions": narrative.strip()[:2000],
        "diagnosis_codes": [],
        "medications": [],
        "observations": [],
    }


def parse_doctor_letter(content: str | bytes, filename: str | None = None) -> dict[str, Any]:
    text = content.decode() if isinstance(content, bytes) else content
    if text.lstrip().startswith("{"):
        return _parse_json(json.loads(text))
    return _parse_xml(text)
