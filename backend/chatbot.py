"""Prescription-scoped chatbot powered by Gemini."""

from __future__ import annotations

import json
from typing import Any

from .gemini_client import _generate_text, is_available
from .logging_config import get_logger

log = get_logger("chatbot")

OFF_TOPIC_REPLY = (
    "I can only help with questions about **your current e-prescription** shown on this page "
    "(medication, insurance, prescriber, how to use it at the pharmacy, etc.). "
    "I can't answer questions about other people's prescriptions or unrelated topics."
)

DISCLAIMER = (
    "This is general information based on your prescription data — not medical advice. "
    "Always follow your doctor or pharmacist for personal medical decisions."
)


def _build_context_block(parsed: dict[str, Any], humanized: dict[str, Any]) -> str:
    return json.dumps(
        {
            "parsed_fields": parsed,
            "plain_language_summary": humanized.get("patient_summary"),
            "sections": humanized.get("sections"),
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


def chat_about_prescription(
    message: str,
    parsed: dict[str, Any],
    humanized: dict[str, Any],
    history: list[dict[str, str]] | None = None,
    lang: str = "en",
) -> dict[str, Any]:
    if not is_available():
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

    prompt = f"""You are a helpful patient assistant for a German e-prescription (E-Rezept) viewer demo.

STRICT RULES:
1. Answer ONLY questions related to the patient's CURRENT prescription data provided below.
2. Allowed topics: medication on this prescription, dosage form, quantity, co-payment, insurance on this Rx, prescriber/practice, prescription status, how to redeem at pharmacy, what the summary means, general education about terms ON this prescription.
3. If the user asks about another person's prescription, unrelated medical conditions not on this Rx, general news, coding, homework, or anything not grounded in THIS prescription data — respond with on_topic=false and a brief polite refusal (do not answer the off-topic question).
4. You may explain medical terms (e.g. what co-payment means) ONLY as they apply to THIS prescription.
5. Do NOT diagnose, change dosage, or replace a doctor/pharmacist. Add a brief reminder when giving medical-style explanations.
6. Reply in language code "{target_lang}" unless the user writes in another language — then match their language.
7. Be concise (2-5 sentences unless they ask for detail).

PRESCRIPTION DATA (your only source of truth):
{context}

CHAT HISTORY:
{hist}

USER QUESTION:
{message}

Return ONLY valid JSON:
{{
  "on_topic": true or false,
  "reply": "your response to the user"
}}"""

    raw = _generate_text(prompt, json_mode=True)
    if not raw:
        log.warning("Gemini chat returned empty for prescription=%s", parsed.get("prescription_id"))
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
        if on_topic and reply:
            reply = f"{reply}\n\n⚕ {DISCLAIMER}"
        log.info(
            "chat prescription=%s on_topic=%s q_len=%d",
            parsed.get("prescription_id"),
            on_topic,
            len(message),
        )
        return {"reply": reply, "on_topic": on_topic, "available": True}
    except (json.JSONDecodeError, KeyError):
        log.exception("Failed to parse Gemini chat response")
        return {
            "reply": raw[:2000] if raw else "Sorry, something went wrong.",
            "on_topic": True,
            "available": True,
        }
