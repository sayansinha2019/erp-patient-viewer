"""Follow-up appointment detection from discharge / doctor letters."""

from __future__ import annotations

import re
from typing import Any


def detect_follow_up_flags(parsed: dict[str, Any], lang: str = "en") -> list[dict[str, str]]:
    text = " ".join(
        str(parsed.get(k) or "")
        for k in ("follow_up_instruction", "clinical_narrative", "patient_instructions")
    )
    flags = []
    match = re.search(r"(\d+)\s*(wochen|weeks|monate|months)", text.lower())
    if match:
        flags.append({
            "severity": "advisory",
            "title": "Follow-up recommended",
            "body": (
                f"Your document recommends a follow-up within about {match.group(0)}. "
                "Have you booked this appointment yet?"
            ),
            "code": "follow_up_due",
        })
    if re.search(r"kardiolog|nephrolog|diabetolog|facharzt|specialist", text.lower()):
        flags.append({
            "severity": "informational",
            "title": "Specialist follow-up mentioned",
            "body": "A specialist appointment is mentioned. Worth booking if you have not already.",
            "code": "specialist_follow_up",
        })
    return flags
