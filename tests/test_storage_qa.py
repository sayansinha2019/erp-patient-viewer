"""Storage and clinical QA tests."""

import pytest

from backend import storage
from backend.clinical_qa import load_ground_truth_cases, validate_output_against_ground_truth
from backend.pipeline import process_document
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent


def test_register_and_timeline(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    user = storage.register_user("helga@example.com", "secure-pass-123")
    assert user["token"]
    assert user["user_id"]
    record = {
        "document_type": "lab_result",
        "document_title": "Lab test",
        "flags": [],
        "humanized": {"patient_summary": "Test summary"},
        "parsed": {"observations": [{"loinc_code": "4548-4", "value": 7.0}]},
    }
    rid = storage.save_health_record(user["user_id"], "secure-pass-123", record)
    timeline = storage.list_timeline(user["user_id"], "secure-pass-123")
    assert len(timeline) == 1
    assert timeline[0]["id"] == rid


def test_ground_truth_cases_exist():
    cases = load_ground_truth_cases()
    assert len(cases) >= 1


def test_clinical_qa_lab_case():
    case_path = APP_DIR / "data" / "ground_truth" / "lab_result_diabetes.json"
    if not case_path.exists():
        pytest.skip("ground truth missing")
    sample = APP_DIR / "data" / "samples" / "documents" / "lab_result_diabetes.json"
    out = process_document(sample.read_bytes(), filename=sample.name, lang="de", mode="offline")
    result = validate_output_against_ground_truth("lab_result_diabetes", out)
    assert result["passed"] is True
