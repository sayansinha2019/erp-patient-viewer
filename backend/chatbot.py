"""Document-scoped chatbot — explains this document plus general health literacy."""

from __future__ import annotations

import json
import re
from typing import Any

from .gemini_client import _generate_text, is_available
from .logging_config import get_logger

log = get_logger("chatbot")

OFF_TOPIC_REPLY = (
    "I can help with questions about your current document and how German healthcare works "
    "(e-prescriptions, lab results, referrals, pharmacy visits, appointments). "
    "I can't answer unrelated topics like weather or other people's medical records."
)

DISCLAIMER = (
    "This is general information — not medical advice. "
    "Always follow your doctor or pharmacist for personal decisions."
)

REFUSAL_PATTERNS = (
    "does not contain",
    "only provide information directly related",
    "i can only help",
    "not contain any details",
    "no details about",
    "cannot answer",
    "can't answer",
)


def _build_context_block(parsed: dict[str, Any], humanized: dict[str, Any]) -> str:
    return json.dumps(
        {
            "document_type": parsed.get("document_type"),
            "parsed_fields": parsed,
            "plain_language_summary": humanized.get("patient_summary"),
            "sections": humanized.get("sections"),
            "flags": humanized.get("flags") if isinstance(humanized.get("flags"), list) else None,
            "language": humanized.get("target_language", "en"),
        },
        ensure_ascii=False,
        indent=2,
    )


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(no prior messages)"
    lines = []
    for msg in history[-8:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def _normalize(msg: str) -> str:
    return re.sub(r"\s+", " ", msg.lower().strip())


def _field_hint(parsed: dict[str, Any], humanized: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = parsed.get(key)
        if val not in (None, "", "null"):
            return str(val)
    blob = json.dumps(humanized.get("sections") or {}, ensure_ascii=False).lower()
    for key in keys:
        if key.replace("_", " ") in blob or key in blob:
            return f"mentioned in your document summary ({key})"
    return None


def _looks_refusal(reply: str) -> bool:
    lower = reply.lower()
    return any(p in lower for p in REFUSAL_PATTERNS)


def _educational_reply(message: str, parsed: dict[str, Any], humanized: dict[str, Any], lang: str) -> str | None:
    """Plain-language answers for common questions — no personal data required."""
    q = _normalize(message)
    copay_hint = _field_hint(parsed, humanized, "copayment", "copay", "zuzahlung")

    if any(t in q for t in ("co-payment", "co payment", "copayment", "zuzahlung", "zuzahlen")):
        base = (
            "A co-payment (Zuzahlung) is the small amount you may pay at the pharmacy yourself — "
            "on top of what your German health insurance covers. "
            "Not every prescription has one; it depends on the medicine and your insurance status."
        )
        if copay_hint:
            base += f" On your document, the co-payment status is: {copay_hint}."
        else:
            base += " Your document does not list a specific amount — the pharmacy will tell you at pickup."
        base += " You can also ask the pharmacy staff to explain the amount before they dispense."
        return base

    if any(t in q for t in ("pharmacy", "redeem", "einlösen", "pick up", "collect", "apotheke")):
        return (
            "To use an e-prescription in Germany: go to any pharmacy with your electronic health card (eGK) "
            "or the app your insurer provides. The pharmacist retrieves the prescription digitally — "
            "you usually do not need a paper printout. "
            "If a co-payment applies, you pay it at the counter. "
            "Ask the pharmacist if anything on your summary is unclear."
        )

    if any(t in q for t in ("book", "appointment", "termin", "specialist", "facharzt", "überweisung", "referral")):
        follow = parsed.get("follow_up_instruction") or parsed.get("clinical_narrative", "")[:200]
        extra = ""
        if follow and any(w in follow.lower() for w in ("woche", "week", "termin", "kontrolle", "nephrolog", "kardiolog")):
            extra = " Your document mentions a follow-up — ask your GP's office for a referral (Überweisung) if needed."
        return (
            "To book a specialist in Germany: call your GP (Hausarzt) or the specialist practice directly. "
            "Mention you have a referral (Überweisung) if your document includes one. "
            "For public insurance, booking by phone is still common; some practices offer Doctolib or Jameda online."
            + extra
            + " If urgent, say so when you call — or contact your GP's on-call service."
        )

    if any(t in q for t in ("generic", "substitut", "alternative")):
        sub = parsed.get("substitution_allowed")
        if sub is not None:
            return (
                f"Generic substitution on your prescription: {sub}. "
                "If substitution is not allowed, the pharmacy should give the exact product prescribed "
                "unless your doctor agrees to a change."
            )
        return (
            "A generic substitute is a cheaper medicine with the same active ingredient. "
            "In Germany, pharmacies may offer one unless your prescription says substitution is not allowed."
        )

    if any(t in q for t in ("what was prescribed", "medication", "medikament", "which drug")):
        med = parsed.get("medication_name")
        if med:
            return f"Your document lists this medication: {med}. Ask your pharmacist how and when to take it."
        meds = parsed.get("medications") or []
        if meds:
            names = ", ".join(m.get("name", "") for m in meds if m.get("name"))
            if names:
                return f"Medications mentioned: {names}. Your doctor or pharmacist can explain how to take them."
        return None

    return None


def chat_about_prescription(
    message: str,
    parsed: dict[str, Any],
    humanized: dict[str, Any],
    history: list[dict[str, str]] | None = None,
    lang: str = "en",
) -> dict[str, Any]:
    if not is_available():
        edu = _educational_reply(message, parsed, humanized, lang)
        if edu:
            return {"reply": f"{edu}\n\n⚕ {DISCLAIMER}", "on_topic": True, "available": False}
        return {
            "reply": "Chat is unavailable — Gemini API key not configured.",
            "on_topic": False,
            "available": False,
        }

    message = (message or "").strip()
    if not message:
        return {"reply": "Please type a question.", "on_topic": True, "available": True}

    context = _build_context_block(parsed, humanized)
    hist = _format_history(history or [])
    target_lang = humanized.get("target_language") or lang
    doc_type = parsed.get("document_type", "health document")

    prompt = f"""You are Klarify — a calm patient assistant for German health documents (e-prescriptions, lab reports, discharge letters, referrals).

YOUR JOB:
1. Help the patient understand THEIR CURRENT document (data below).
2. Explain general healthcare concepts and practical steps when asked — co-payment (Zuzahlung), pharmacy visits, e-Rezept redemption, booking appointments, referrals, lab terms. This is allowed and encouraged.
3. Use the document data when it exists; if a field is missing, still give a clear general explanation. Never refuse just because a field is empty.
4. Do NOT invent personal medical facts (doses, diagnoses) not in the document. You MAY explain what terms mean in general and what patients usually do next in Germany.

OFF-TOPIC (on_topic=false): weather, politics, coding, homework, other people's records, unrelated chit-chat.

NOT ALLOWED: diagnosing, changing medication doses, telling them to stop treatment.

Reply in language code "{target_lang}" (match user language if they write differently).
Be warm, plain, 2-6 sentences unless they want detail.

DOCUMENT TYPE: {doc_type}
DOCUMENT DATA (use when present; supplement with general knowledge when needed):
{context}

CHAT HISTORY:
{hist}

USER QUESTION:
{message}

Return ONLY valid JSON:
{{
  "on_topic": true or false,
  "reply": "your response"
}}"""

    raw = _generate_text(prompt, json_mode=True)
    if not raw:
        edu = _educational_reply(message, parsed, humanized, lang)
        if edu:
            return {"reply": f"{edu}\n\n⚕ {DISCLAIMER}", "on_topic": True, "available": True}
        return {
            "reply": "Sorry, I couldn't generate a response. Please try again.",
            "on_topic": True,
            "available": True,
        }

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        data = json.loads(cleaned)
        on_topic = bool(data.get("on_topic", True))
        reply = data.get("reply", "").strip()

        if not on_topic and not reply:
            reply = OFF_TOPIC_REPLY

        # If model wrongly refused an educational question, use built-in explainer
        if on_topic and reply and _looks_refusal(reply):
            edu = _educational_reply(message, parsed, humanized, lang)
            if edu:
                reply = edu
                on_topic = True

        if not on_topic:
            edu = _educational_reply(message, parsed, humanized, lang)
            if edu:
                reply = edu
                on_topic = True

        if on_topic and reply:
            reply = f"{reply}\n\n⚕ {DISCLAIMER}"

        log.info(
            "chat doc_type=%s on_topic=%s q_len=%d",
            doc_type,
            on_topic,
            len(message),
        )
        return {"reply": reply, "on_topic": on_topic, "available": True}
    except (json.JSONDecodeError, KeyError):
        log.exception("Failed to parse Gemini chat response")
        edu = _educational_reply(message, parsed, humanized, lang)
        if edu:
            return {"reply": f"{edu}\n\n⚕ {DISCLAIMER}", "on_topic": True, "available": True}
        return {
            "reply": raw[:2000] if raw else "Sorry, something went wrong.",
            "on_topic": True,
            "available": True,
        }
