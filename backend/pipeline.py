"""Klarify unified document pipeline — all four layers."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from .document_humanizer import build_cards_for_document, humanize_document
from .document_router import parse_document
from .flagging import generate_all_flags
from .logging_config import get_logger
from .output_validator import validate_flags, validate_humanized
from .pdf_ingest import parse_pdf_document
from .rag_engine import generate_explanation
from .settings import zero_retention_enabled
from .translator import translate_humanized
from .languages import SUPPORTED_LANGUAGES

log = get_logger("pipeline")

_SESSION_AUDIT: list[dict[str, str]] = []


def _audit_session(document_type: str, lang: str) -> str:
    session_id = str(uuid.uuid4())
    if zero_retention_enabled():
        _SESSION_AUDIT.append({"session_id": session_id, "document_type": document_type, "lang": lang})
        if len(_SESSION_AUDIT) > 500:
            _SESSION_AUDIT.pop(0)
    return session_id


def process_document(
    content: str | bytes,
    *,
    filename: str = "upload.xml",
    lang: str = "de",
    mode: Optional[str] = None,
    source: str = "upload",
) -> dict[str, Any]:
    """
    Full Klarify pipeline for any supported document type.

    L4 — Parse (FHIR / PDF)
    L1 — RAG + translate
    L2 — Clinical flags
    L3 — Zero-retention (unless user saves via storage API)
    """
    is_pdf = filename.lower().endswith(".pdf")
    if is_pdf:
        parsed = parse_pdf_document(content if isinstance(content, bytes) else content.encode())
        doc_type = parsed.get("document_type", "doctor_letter")
    else:
        parsed = parse_document(content, filename=filename)
        doc_type = parsed.get("document_type", "prescription")

    session_id = _audit_session(doc_type, lang)
    lang_name = SUPPORTED_LANGUAGES.get(lang, lang)

    # L1 — Humanize base + RAG enrichment
    humanized = humanize_document(parsed, doc_type)
    rag = generate_explanation(parsed, doc_type, lang, lang_name)
    if rag and rag.get("patient_summary"):
        humanized["patient_summary"] = rag["patient_summary"]
        humanized["rag_provider"] = rag.get("rag_provider")

    humanized = translate_humanized(humanized, lang, parsed=parsed, mode=mode)
    humanized = validate_humanized(humanized)

    # L2 — Clinical flagging
    flags = validate_flags(generate_all_flags(parsed, doc_type, lang=lang))

    cards = build_cards_for_document(parsed, humanized, doc_type)

    # Low-confidence PDF extraction flag
    if parsed.get("extraction_confidence", 1.0) < 0.6:
        flags.append({
            "severity": "advisory",
            "title": "Please verify extracted text",
            "body": "We had difficulty reading this PDF clearly. Check that the summary matches your document.",
            "code": "pdf_low_confidence",
        })

    return {
        "parsed": parsed,
        "humanized": humanized,
        "flags": flags,
        "explanation_cards": cards,
        "document_type": doc_type,
        "document_title": parsed.get("document_title") or doc_type.replace("_", " ").title(),
        "session_id": session_id,
        "source": source,
        "pipeline": {
            "l1_translation": {
                "status": "ok",
                "provider": humanized.get("translation_provider") or humanized.get("rag_provider"),
                "rag": bool(rag),
            },
            "l2_flagging": {"status": "ok", "flag_count": len(flags)},
            "l3_storage": {"status": "skipped", "reason": "zero_retention"},
            "l4_fhir": {"status": "ok", "source": parsed.get("source", source)},
        },
        "zero_retention": zero_retention_enabled(),
    }


def process_prescription(content: str | bytes, **kwargs) -> dict[str, Any]:
    """Backward-compatible entry for prescriptions."""
    return process_document(content, **kwargs)
