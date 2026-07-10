"""Clinical QA — ground truth validation for Head of Clinical Affairs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GROUND_TRUTH_DIR = Path(__file__).resolve().parent.parent / "data" / "ground_truth"
APP_DIR = Path(__file__).resolve().parent.parent


def load_ground_truth_cases() -> list[dict[str, Any]]:
    if not GROUND_TRUTH_DIR.exists():
        return []
    cases = []
    for path in sorted(GROUND_TRUTH_DIR.glob("*.json")):
        cases.append(json.loads(path.read_text(encoding="utf-8")))
    return cases


def validate_output_against_ground_truth(
    case_id: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    cases = {c["id"]: c for c in load_ground_truth_cases()}
    case = cases.get(case_id)
    if not case:
        return {"passed": False, "error": f"Unknown case {case_id}"}

    issues = []
    expected = case.get("expect", {})

    summary = (output.get("humanized") or {}).get("patient_summary", "") or ""
    for phrase in expected.get("summary_contains", []):
        if phrase.lower() not in summary.lower():
            issues.append(f"Summary missing expected phrase: {phrase}")

    for code in expected.get("flag_codes", []):
        codes = [f.get("code") for f in output.get("flags", [])]
        if code not in codes:
            issues.append(f"Missing expected flag: {code}")

    for forbidden in expected.get("forbidden_phrases", []):
        blob = json.dumps(output, ensure_ascii=False).lower()
        if forbidden.lower() in blob:
            issues.append(f"Forbidden phrase found: {forbidden}")

    min_obs = expected.get("observations_min", 0)
    if min_obs:
        count = len((output.get("parsed") or {}).get("observations", []))
        if count < min_obs:
            issues.append(f"Expected at least {min_obs} observations, got {count}")

    return {
        "case_id": case_id,
        "passed": len(issues) == 0,
        "issues": issues,
        "validated_by": "automated_ground_truth",
    }


def run_all_qa(pipeline_fn) -> dict[str, Any]:
    """Run ground truth suite against pipeline function."""
    results = []
    for case in load_ground_truth_cases():
        sample = APP_DIR / case["sample"]
        if not sample.exists():
            results.append({"id": case["id"], "passed": False, "error": "sample missing"})
            continue
        content = sample.read_bytes()
        out = pipeline_fn(content, filename=sample.name, lang=case.get("lang", "de"))
        validation = validate_output_against_ground_truth(case["id"], out)
        results.append(validation)
    passed = sum(1 for r in results if r.get("passed"))
    return {"total": len(results), "passed": passed, "results": results}
