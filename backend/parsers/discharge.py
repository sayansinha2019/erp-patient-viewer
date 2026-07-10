"""Parse FHIR Composition — hospital discharge letter (Entlassbrief)."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any

from ..dictionaries.clinical_index import resolve_icd10

FHIR_NS = {"f": "http://hl7.org/fhir"}


def _extract_icd_codes(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\b[A-Z][0-9]{2}(?:\.[0-9]{1,2})?\b", text or "")))


def _parse_json(data: dict) -> dict[str, Any]:
    composition = next(
        (e["resource"] for e in data.get("entry", []) if e.get("resource", {}).get("resourceType") == "Composition"),
        {},
    )
    narrative = ""
    for section in composition.get("section", []):
        text = section.get("text", {}).get("div", "")
        narrative += " " + re.sub(r"<[^>]+>", " ", text)
    codes = _extract_icd_codes(narrative)
    diagnoses = [{"code": c, "description": resolve_icd10(c)} for c in codes]
    meds = []
    for entry in data.get("entry", []):
        if entry.get("resource", {}).get("resourceType") == "MedicationRequest":
            m = entry["resource"]
            name = m.get("medicationCodeableConcept", {}).get("text", "")
            atc = None
            lower = name.lower()
            if "metformin" in lower:
                atc = "A10BA02"
            elif "enalapril" in lower:
                atc = "C09AA02"
            meds.append({"name": name, "atc_code": atc})
    follow_up = ""
    if re.search(r"(\d+)\s*(wochen|weeks)", narrative.lower()):
        follow_up = re.search(r"(\d+)\s*(wochen|weeks)", narrative.lower()).group(0)
    return {
        "document_title": composition.get("title") or "Entlassbrief",
        "discharge_date": composition.get("date"),
        "clinical_narrative": narrative.strip()[:4000],
        "diagnosis_codes": codes,
        "diagnoses": diagnoses,
        "medications": meds,
        "follow_up_instruction": follow_up or narrative[:500],
    }


def _parse_xml(content: str) -> dict[str, Any]:
    root = ET.fromstring(content)
    title = None
    narrative = ""
    for entry in root.findall("f:entry", FHIR_NS):
        comp = entry.find(".//f:Composition", FHIR_NS)
        if comp is not None:
            t = comp.find("f:title", FHIR_NS)
            title = t.get("value") if t is not None else "Entlassbrief"
            for section in comp.findall(".//f:section", FHIR_NS):
                text_el = section.find(".//f:div", FHIR_NS)
                if text_el is not None and text_el.text:
                    narrative += " " + text_el.text
    codes = _extract_icd_codes(narrative)
    return {
        "document_title": title or "Entlassbrief",
        "clinical_narrative": narrative.strip(),
        "diagnosis_codes": codes,
        "diagnoses": [{"code": c, "description": resolve_icd10(c)} for c in codes],
        "medications": [],
        "follow_up_instruction": narrative[:500],
    }


def parse_discharge(content: str | bytes, filename: str | None = None) -> dict[str, Any]:
    text = content.decode() if isinstance(content, bytes) else content
    if text.lstrip().startswith("{"):
        return _parse_json(json.loads(text))
    return _parse_xml(text)
