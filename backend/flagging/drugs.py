"""Drug interaction detection via ATC pairs."""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

INTERACTIONS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "clinical" / "drug_interactions.json"


def _load_interactions() -> list[dict]:
    if not INTERACTIONS_PATH.exists():
        return []
    return json.loads(INTERACTIONS_PATH.read_text(encoding="utf-8"))


def _collect_atc_codes(parsed: dict[str, Any]) -> list[str]:
    codes = []
    for med in parsed.get("medications", []) or []:
        if med.get("atc_code"):
            codes.append(med["atc_code"])
    if parsed.get("atc_code"):
        codes.append(parsed["atc_code"])
    return list(dict.fromkeys(codes))


def check_drug_interactions(parsed: dict[str, Any], lang: str = "en") -> list[dict[str, str]]:
    atc_codes = _collect_atc_codes(parsed)
    if len(atc_codes) < 2:
        return []
    interactions = _load_interactions()
    flags = []
    for a, b in combinations(atc_codes, 2):
        for row in interactions:
            pair = {row.get("atc_a"), row.get("atc_b")}
            if pair == {a, b}:
                sev = "urgent" if row.get("severity") in ("major", "contraindicated") else "advisory"
                flags.append({
                    "severity": sev,
                    "title": "Possible medication interaction",
                    "body": (
                        "These two medications may interact. Please confirm with your doctor or pharmacist "
                        "that both are appropriate for you to take together."
                    ),
                    "code": f"interaction_{a}_{b}",
                    "description": row.get("description"),
                })
    return flags
