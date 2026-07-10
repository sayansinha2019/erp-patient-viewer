"""LOINC reference range flagging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RANGES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "clinical" / "loinc_ranges.json"


def _load_ranges() -> dict:
    if not RANGES_PATH.exists():
        return {}
    return json.loads(RANGES_PATH.read_text(encoding="utf-8"))


def _classify(value: float, ref: dict) -> str | None:
    normal = ref.get("normal", [0, 999])
    borderline = ref.get("borderline", normal)
    critical = ref.get("critical", [999, 9999])
    if normal[0] <= value <= normal[1]:
        return None
    if borderline[0] <= value <= borderline[1]:
        return "informational"
    if value <= critical[1] and value >= critical[0]:
        return "urgent"
    return "advisory"


def generate_lab_flags(parsed: dict[str, Any], lang: str = "en") -> list[dict[str, str]]:
    flags = []
    ranges = _load_ranges()
    for obs in parsed.get("observations", []) or []:
        loinc = obs.get("loinc_code")
        value = obs.get("value")
        if loinc not in ranges or value is None:
            continue
        try:
            value_f = float(value)
        except (TypeError, ValueError):
            continue
        ref = ranges[loinc]
        severity = _classify(value_f, ref)
        if not severity:
            continue
        name = ref.get("name") or obs.get("display") or loinc
        unit = obs.get("unit") or ref.get("unit", "")
        body_en = (
            f"Your {name} result is {value_f} {unit}. "
            f"This is worth discussing at your next appointment."
            if severity != "urgent"
            else f"Your {name} result is {value_f} {unit}. Please speak with your doctor or pharmacist."
        )
        flags.append({
            "severity": severity,
            "title": name,
            "body": body_en,
            "code": f"lab_{loinc}",
            "loinc": loinc,
            "value": value_f,
        })
    return flags
