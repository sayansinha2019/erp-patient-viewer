"""Parse FHIR DiagnosticReport + Observation (lab results)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

FHIR_NS = {"f": "http://hl7.org/fhir"}


def _parse_json_bundle(data: dict) -> dict[str, Any]:
    observations = []
    report_title = None
    report_date = None
    patient_name = None

    for entry in data.get("entry", []):
        res = entry.get("resource", {})
        rtype = res.get("resourceType")
        if rtype == "DiagnosticReport":
            report_title = res.get("code", {}).get("text") or "Laborbericht"
            report_date = res.get("effectiveDateTime") or res.get("issued")
        elif rtype == "Observation":
            code = (res.get("code", {}).get("coding") or [{}])[0]
            value_qty = res.get("valueQuantity", {})
            interp = (res.get("interpretation") or [{}])[0]
            ref = (res.get("referenceRange") or [{}])[0]
            observations.append({
                "loinc_code": code.get("code"),
                "display": res.get("code", {}).get("text") or code.get("display"),
                "value": value_qty.get("value"),
                "unit": value_qty.get("unit"),
                "interpretation": interp.get("text") or (interp.get("coding") or [{}])[0].get("code"),
                "reference_low": (ref.get("low") or {}).get("value"),
                "reference_high": (ref.get("high") or {}).get("value"),
            })
        elif rtype == "Patient":
            names = res.get("name", [])
            if names:
                n = names[0]
                patient_name = " ".join(filter(None, [n.get("family"), " ".join(n.get("given", []))]))

    return {
        "document_title": report_title or "Lab report",
        "report_date": report_date,
        "patient_name": patient_name,
        "observations": observations,
        "diagnosis_codes": [],
        "medications": [],
    }


def _parse_xml(content: str) -> dict[str, Any]:
    root = ET.fromstring(content)
    observations = []
    title = None
    for entry in root.findall("f:entry", FHIR_NS):
        res = entry.find("f:resource", FHIR_NS)
        if res is None:
            continue
        if res.find("f:DiagnosticReport", FHIR_NS) is not None:
            dr = res.find("f:DiagnosticReport", FHIR_NS)
            t = dr.find("f:code/f:text", FHIR_NS)
            title = t.get("value") if t is not None else "Laborbericht"
        obs = res.find("f:Observation", FHIR_NS)
        if obs is not None:
            code_el = obs.find(".//f:code/f:coding/f:code", FHIR_NS)
            display = obs.find("f:code/f:text", FHIR_NS)
            val = obs.find("f:valueQuantity/f:value", FHIR_NS)
            unit = obs.find("f:valueQuantity/f:unit", FHIR_NS)
            observations.append({
                "loinc_code": code_el.get("value") if code_el is not None else None,
                "display": display.get("value") if display is not None else None,
                "value": float(val.get("value")) if val is not None else None,
                "unit": unit.get("value") if unit is not None else None,
            })
    return {
        "document_title": title or "Lab report",
        "observations": observations,
        "diagnosis_codes": [],
        "medications": [],
    }


def parse_lab(content: str | bytes, filename: str | None = None) -> dict[str, Any]:
    text = content.decode() if isinstance(content, bytes) else content
    if text.lstrip().startswith("{"):
        return _parse_json_bundle(json.loads(text))
    return _parse_xml(text)
