"""Parse gematik E-Rezept FHIR Bundles (XML or JSON) into a flat dictionary."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

FHIR_NS = {"f": "http://hl7.org/fhir"}


def _text(el: ET.Element | None, tag: str = "value") -> str | None:
    if el is None:
        return None
    child = el.find(f"f:{tag}", FHIR_NS)
    if child is not None and child.get("value"):
        return child.get("value")
    nested = el.find(f"f:{tag}", FHIR_NS)
    if nested is not None and nested.text:
        return nested.text.strip()
    return el.get("value")


def _find_resource(bundle_root: ET.Element, resource_type: str) -> ET.Element | None:
    for entry in bundle_root.findall("f:entry", FHIR_NS):
        resource = entry.find("f:resource", FHIR_NS)
        if resource is not None and resource.find(f"f:{resource_type}", FHIR_NS) is not None:
            return resource.find(f"f:{resource_type}", FHIR_NS)
    return None


def _find_all_resources(bundle_root: ET.Element, resource_type: str) -> list[ET.Element]:
    results = []
    for entry in bundle_root.findall("f:entry", FHIR_NS):
        resource = entry.find("f:resource", FHIR_NS)
        if resource is not None:
            node = resource.find(f"f:{resource_type}", FHIR_NS)
            if node is not None:
                results.append(node)
    return results


def _extension_code(resource: ET.Element, url_fragment: str) -> str | None:
    for ext in resource.findall("f:extension", FHIR_NS):
        url = ext.get("url", "")
        if url_fragment in url:
            coding = ext.find(".//f:valueCoding/f:code", FHIR_NS)
            if coding is not None:
                return coding.get("value")
            boolean = ext.find("f:valueBoolean", FHIR_NS)
            if boolean is not None:
                return boolean.get("value")
    return None


def _patient_name(patient: ET.Element) -> str | None:
    name = patient.find("f:name", FHIR_NS)
    if name is None:
        return None
    parts = []
    prefix = _text(name.find("f:prefix", FHIR_NS))
    given = _text(name.find("f:given", FHIR_NS))
    family_el = name.find("f:family", FHIR_NS)
    family = family_el.get("value") if family_el is not None else None
    if prefix:
        parts.append(prefix)
    if given:
        parts.append(given)
    if family:
        parts.append(family)
    return " ".join(parts) if parts else None


def _address(resource: ET.Element) -> str | None:
    addr = resource.find("f:address", FHIR_NS)
    if addr is None:
        return None
    line = _text(addr.find("f:line", FHIR_NS))
    city = _text(addr.find("f:city", FHIR_NS))
    postal = _text(addr.find("f:postalCode", FHIR_NS))
    country = _text(addr.find("f:country", FHIR_NS))
    parts = [p for p in [line, f"{postal} {city}".strip() if city or postal else None, country] if p]
    return ", ".join(parts) if parts else None


def _practitioner_specialty(practitioner: ET.Element) -> str | None:
    for qual in practitioner.findall("f:qualification", FHIR_NS):
        text_el = qual.find(".//f:text", FHIR_NS)
        if text_el is not None and text_el.get("value"):
            return text_el.get("value")
    return None


def _multiple_prescription_info(med_req: ET.Element) -> dict[str, str | None]:
    for ext in med_req.findall("f:extension", FHIR_NS):
        if "KBV_EX_ERP_Multiple_Prescription" in ext.get("url", ""):
            number = None
            period = None
            flag = None
            for sub in ext.findall("f:extension", FHIR_NS):
                url = sub.get("url", "")
                if url == "Kennzeichen":
                    flag = _text(sub.find("f:valueBoolean", FHIR_NS))
                elif url == "Nummerierung":
                    num = sub.find(".//f:numerator/f:value", FHIR_NS)
                    den = sub.find(".//f:denominator/f:value", FHIR_NS)
                    if num is not None and den is not None:
                        number = f"{num.get('value')} of {den.get('value')}"
                elif url == "Zeitraum":
                    start = _text(sub.find(".//f:start", FHIR_NS))
                    end = _text(sub.find(".//f:end", FHIR_NS))
                    if start or end:
                        period = f"{start or '?'} to {end or '?'}"
            return {"flag": flag, "number": number, "period": period}
    return {"flag": None, "number": None, "period": None}


def parse_fhir_xml(content: str | bytes) -> dict[str, Any]:
    root = ET.fromstring(content)
    bundle_id = _text(root.find("f:id", FHIR_NS))
    prescription_id = None
    identifier = root.find("f:identifier", FHIR_NS)
    if identifier is not None:
        prescription_id = _text(identifier.find("f:value", FHIR_NS))

    composition = _find_resource(root, "Composition")
    med_req = _find_resource(root, "MedicationRequest")
    medication = _find_resource(root, "Medication")
    patient = _find_resource(root, "Patient")
    practitioner = _find_resource(root, "Practitioner")
    organization = _find_resource(root, "Organization")
    coverage = _find_resource(root, "Coverage")

    legal_basis = None
    form_type = None
    document_title = None
    prescription_date = None
    if composition is not None:
        legal_basis = _extension_code(composition, "KBV_EX_FOR_Legal_basis")
        document_title = _text(composition.find("f:title", FHIR_NS))
        prescription_date = _text(composition.find("f:date", FHIR_NS))
        type_coding = composition.find(".//f:type/f:coding/f:code", FHIR_NS)
        if type_coding is not None:
            form_type = type_coding.get("value")

    medication_name = None
    pzn = None
    dosage_form_code = None
    if medication is not None:
        code = medication.find("f:code", FHIR_NS)
        if code is not None:
            medication_name = _text(code.find("f:text", FHIR_NS))
            for coding in code.findall("f:coding", FHIR_NS):
                system_el = coding.find("f:system", FHIR_NS)
                code_el = coding.find("f:code", FHIR_NS)
                system_val = system_el.get("value", "") if system_el is not None else ""
                if code_el is not None and "pzn" in system_val.lower():
                    pzn = code_el.get("value")
                    break
        if not medication_name:
            ing = medication.find(".//f:ingredient/f:itemCodeableConcept/f:text", FHIR_NS)
            if ing is not None and ing.get("value"):
                medication_name = ing.get("value")
                strength = medication.find(".//f:ingredient/f:strength/f:numerator/f:value", FHIR_NS)
                unit = medication.find(".//f:ingredient/f:strength/f:numerator/f:unit", FHIR_NS)
                if strength is not None:
                    suffix = f" {strength.get('value')}"
                    if unit is not None and unit.get("value"):
                        suffix += f" {unit.get('value')}"
                    medication_name += suffix
        form_coding = medication.find(".//f:form/f:coding/f:code", FHIR_NS)
        if form_coding is not None:
            dosage_form_code = form_coding.get("value")
        if not dosage_form_code:
            form_text = medication.find(".//f:form/f:text", FHIR_NS)
            if form_text is not None and form_text.get("value"):
                dosage_form_code = form_text.get("value")

    status = _text(med_req.find("f:status", FHIR_NS)) if med_req is not None else None
    authored_on = _text(med_req.find("f:authoredOn", FHIR_NS)) if med_req is not None else None
    copayment = _extension_code(med_req, "KBV_EX_ERP_StatusCoPayment") if med_req is not None else None
    mvo = _multiple_prescription_info(med_req) if med_req is not None else {}

    quantity = None
    substitution = None
    if med_req is not None:
        qty_val = med_req.find(".//f:dispenseRequest/f:quantity/f:value", FHIR_NS)
        qty_code = med_req.find(".//f:dispenseRequest/f:quantity/f:code", FHIR_NS)
        if qty_val is not None:
            unit = qty_code.get("value", "units") if qty_code is not None else "units"
            quantity = f"{qty_val.get('value')} {unit}"
        sub = med_req.find(".//f:substitution/f:allowedBoolean", FHIR_NS)
        if sub is not None:
            substitution = sub.get("value")

    insurance_id = None
    if patient is not None:
        id_el = patient.find(".//f:identifier/f:value", FHIR_NS)
        if id_el is not None:
            insurance_id = id_el.get("value")

    insurance_fund = None
    insurance_type_code = None
    if coverage is not None:
        payor_display = coverage.find(".//f:payor/f:display", FHIR_NS)
        if payor_display is not None:
            insurance_fund = payor_display.get("value")
        type_coding = coverage.find(".//f:type/f:coding/f:code", FHIR_NS)
        if type_coding is not None:
            insurance_type_code = type_coding.get("value")

    practice_phone = None
    if organization is not None:
        for telecom in organization.findall("f:telecom", FHIR_NS):
            if _text(telecom.find("f:system", FHIR_NS)) == "phone":
                practice_phone = _text(telecom.find("f:value", FHIR_NS))
                break

    return {
        "bundle_id": bundle_id,
        "prescription_id": prescription_id,
        "document_title": document_title,
        "prescription_date": prescription_date or authored_on,
        "status": status,
        "legal_basis": legal_basis,
        "form_type": form_type,
        "patient_name": _patient_name(patient) if patient is not None else None,
        "patient_birth_date": _text(patient.find("f:birthDate", FHIR_NS)) if patient is not None else None,
        "patient_address": _address(patient) if patient is not None else None,
        "insurance_id": insurance_id,
        "insurance_fund": insurance_fund,
        "insurance_type": insurance_type_code,
        "prescriber_name": _patient_name(practitioner) if practitioner is not None else None,
        "prescriber_specialty": _practitioner_specialty(practitioner) if practitioner is not None else None,
        "practice_name": _text(organization.find("f:name", FHIR_NS)) if organization is not None else None,
        "practice_address": _address(organization) if organization is not None else None,
        "practice_phone": practice_phone,
        "medication_name": medication_name,
        "pzn": pzn,
        "dosage_form": dosage_form_code,
        "quantity": quantity,
        "substitution_allowed": substitution,
        "copayment": copayment,
        "multiple_prescription": mvo.get("flag"),
        "multiple_prescription_number": mvo.get("number"),
        "multiple_prescription_period": mvo.get("period"),
        "resource_count": len(_find_all_resources(root, "Patient"))
        + len(_find_all_resources(root, "MedicationRequest"))
        + len(_find_all_resources(root, "Medication")),
    }


def parse_fhir_json(content: str | bytes) -> dict[str, Any]:
    data = json.loads(content)
    if data.get("resourceType") != "Bundle":
        raise ValueError("Expected a FHIR Bundle resource")

    resources: dict[str, list[dict]] = {}
    for entry in data.get("entry", []):
        res = entry.get("resource", {})
        rtype = res.get("resourceType")
        resources.setdefault(rtype, []).append(res)

    def first(rtype: str) -> dict | None:
        items = resources.get(rtype, [])
        return items[0] if items else None

    composition = first("Composition")
    med_req = first("MedicationRequest")
    medication = first("Medication")
    patient = first("Patient")
    practitioner = first("Practitioner")
    organization = first("Organization")
    coverage = first("Coverage")

    def json_name(resource: dict | None) -> str | None:
        if not resource:
            return None
        names = resource.get("name", [])
        if not names:
            return None
        n = names[0]
        parts = []
        if n.get("prefix"):
            parts.extend(n["prefix"] if isinstance(n["prefix"], list) else [n["prefix"]])
        if n.get("given"):
            parts.extend(n["given"] if isinstance(n["given"], list) else [n["given"]])
        if n.get("family"):
            parts.append(n["family"])
        return " ".join(parts) if parts else None

    def json_address(resource: dict | None) -> str | None:
        if not resource:
            return None
        addrs = resource.get("address", [])
        if not addrs:
            return None
        a = addrs[0]
        line = ", ".join(a.get("line", [])) if a.get("line") else None
        city = a.get("city")
        postal = a.get("postalCode")
        country = a.get("country")
        parts = [p for p in [line, f"{postal or ''} {city or ''}".strip() or None, country] if p]
        return ", ".join(parts) if parts else None

    prescription_id = data.get("identifier", {}).get("value")
    med_code = (medication or {}).get("code", {})
    form_code = ((medication or {}).get("form", {}).get("coding") or [{}])[0].get("code")

    return {
        "bundle_id": data.get("id"),
        "prescription_id": prescription_id,
        "document_title": (composition or {}).get("title"),
        "prescription_date": (composition or {}).get("date") or (med_req or {}).get("authoredOn"),
        "status": (med_req or {}).get("status"),
        "legal_basis": None,
        "form_type": ((composition or {}).get("type", {}).get("coding") or [{}])[0].get("code"),
        "patient_name": json_name(patient),
        "patient_birth_date": (patient or {}).get("birthDate"),
        "patient_address": json_address(patient),
        "insurance_id": ((patient or {}).get("identifier") or [{}])[0].get("value"),
        "insurance_fund": ((coverage or {}).get("payor") or [{}])[0].get("display"),
        "insurance_type": ((coverage or {}).get("type", {}).get("coding") or [{}])[0].get("code"),
        "prescriber_name": json_name(practitioner),
        "prescriber_specialty": None,
        "practice_name": (organization or {}).get("name"),
        "practice_address": json_address(organization),
        "practice_phone": next(
            (t.get("value") for t in (organization or {}).get("telecom", []) if t.get("system") == "phone"),
            None,
        ),
        "medication_name": med_code.get("text"),
        "pzn": ((med_code.get("coding") or [{}])[0]).get("code"),
        "dosage_form": form_code,
        "quantity": str((med_req or {}).get("dispenseRequest", {}).get("quantity", {}).get("value", "")),
        "substitution_allowed": str((med_req or {}).get("substitution", {}).get("allowedBoolean", "")),
        "copayment": None,
        "multiple_prescription": None,
        "multiple_prescription_number": None,
        "multiple_prescription_period": None,
        "resource_count": sum(len(v) for v in resources.values()),
    }


def parse_fhir(content: str | bytes, filename: str | None = None) -> dict[str, Any]:
    text = content.decode() if isinstance(content, bytes) else content
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return parse_fhir_json(text)
    if filename and filename.endswith(".json"):
        return parse_fhir_json(text)
    return parse_fhir_xml(text)


def load_sample(path: Path) -> dict[str, Any]:
    return parse_fhir(path.read_bytes(), filename=path.name)
