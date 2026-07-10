"""PDF text extraction + OCR fallback + clinical code pattern matching."""

from __future__ import annotations

import re
from typing import Any

from .document_router import extract_codes_from_text


def extract_pdf_text(content: bytes) -> tuple[str, float]:
    """
    Extract text from PDF. Returns (text, confidence 0-1).
    Uses PyMuPDF; optional Tesseract for scanned pages.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=content, filetype="pdf")
        parts = []
        ocr_pages = 0
        for page in doc:
            text = page.get_text().strip()
            if len(text) < 40:
                ocr_text = _ocr_page(page)
                if ocr_text:
                    text = ocr_text
                    ocr_pages += 1
            parts.append(text)
        full = "\n".join(parts).strip()
        confidence = 0.85 if ocr_pages == 0 else max(0.45, 0.85 - 0.15 * ocr_pages)
        return full, confidence
    except Exception as exc:
        raise ValueError(f"This file cannot be read. Please try a PDF version. ({exc})") from exc


def _ocr_page(page) -> str:
    try:
        import pytesseract
        from PIL import Image
        import io

        pix = page.get_pixmap()
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img, lang="deu+eng")
    except Exception:
        return ""


def parse_pdf_document(content: bytes, filename: str | None = None) -> dict[str, Any]:
    text, confidence = extract_pdf_text(content)
    if not text:
        raise ValueError("No text could be extracted from this PDF.")
    codes = extract_codes_from_text(text)
    doc_type = _guess_pdf_type(text)
    return {
        "document_type": doc_type,
        "document_title": _title_from_text(text, doc_type),
        "source": "pdf",
        "extracted_text": text[:8000],
        "extraction_confidence": confidence,
        "diagnosis_codes": codes.get("diagnosis_codes", []),
        "loinc_codes": codes.get("loinc_codes", []),
        "atc_codes": codes.get("atc_codes", []),
        "medications": [{"atc_code": c} for c in codes.get("atc_codes", [])],
        "observations": _observations_from_text(text, codes.get("loinc_codes", [])),
        "clinical_narrative": text[:4000],
    }


def _guess_pdf_type(text: str) -> str:
    lower = text.lower()
    if "labor" in lower or "befund" in lower or re.search(r"\d{4,5}-\d", text):
        return "lab_result"
    if "entlass" in lower or "discharge" in lower:
        return "discharge"
    if "überweisung" in lower or "referral" in lower:
        return "referral"
    if "rezept" in lower or "verordnung" in lower:
        return "prescription"
    return "doctor_letter"


def _title_from_text(text: str, doc_type: str) -> str:
    first_line = text.split("\n", 1)[0].strip()[:80]
    defaults = {
        "lab_result": "Laborbericht",
        "discharge": "Entlassbrief",
        "referral": "Überweisung",
        "prescription": "Rezept",
        "doctor_letter": "Arztbrief",
    }
    return first_line or defaults.get(doc_type, "Document")


def _observations_from_text(text: str, loinc_codes: list[str]) -> list[dict]:
    obs = []
    for code in loinc_codes:
        pattern = rf"{re.escape(code)}[^\d]*?([\d.,]+)\s*([%a-zA-Z/µ²³]+)?"
        m = re.search(pattern, text)
        if m:
            try:
                val = float(m.group(1).replace(",", "."))
            except ValueError:
                val = None
            obs.append({"loinc_code": code, "value": val, "unit": (m.group(2) or "").strip()})
    return obs
