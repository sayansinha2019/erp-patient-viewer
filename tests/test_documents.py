"""Tests for multi-document pipeline."""

from pathlib import Path

import pytest

from backend.document_router import detect_document_type, parse_document
from backend.dictionaries.clinical_index import resolve_icd10, resolve_loinc
from backend.flagging.lab import generate_lab_flags
from backend.pipeline import process_document

APP_DIR = Path(__file__).resolve().parent.parent
DOC_SAMPLES = APP_DIR / "data" / "samples" / "documents"


@pytest.fixture
def lab_sample():
    path = DOC_SAMPLES / "lab_result_diabetes.json"
    if not path.exists():
        pytest.skip("lab sample missing")
    return path


@pytest.fixture
def discharge_sample():
    path = DOC_SAMPLES / "discharge_diabetes.json"
    if not path.exists():
        pytest.skip("discharge sample missing")
    return path


def test_detect_lab_document(lab_sample):
    content = lab_sample.read_bytes()
    assert detect_document_type(content) == "lab_result"


def test_parse_lab_observations(lab_sample):
    parsed = parse_document(lab_sample.read_bytes(), filename=lab_sample.name)
    assert len(parsed.get("observations", [])) >= 2


def test_lab_flags_hba1c(lab_sample):
    parsed = parse_document(lab_sample.read_bytes(), filename=lab_sample.name)
    flags = generate_lab_flags(parsed)
    codes = [f.get("code") for f in flags]
    assert any("4548-4" in (c or "") for c in codes)


def test_process_lab_pipeline(lab_sample):
    out = process_document(lab_sample.read_bytes(), filename=lab_sample.name, lang="de", mode="offline")
    assert out["document_type"] == "lab_result"
    assert out["pipeline"]["l2_flagging"]["flag_count"] >= 1


def test_process_discharge_follow_up(discharge_sample):
    out = process_document(discharge_sample.read_bytes(), filename=discharge_sample.name, lang="de", mode="offline")
    assert out["document_type"] == "discharge"
    codes = [f.get("code") for f in out.get("flags", [])]
    assert "follow_up_due" in codes


def test_clinical_dictionary_icd():
    assert resolve_icd10("E11.9")
    assert resolve_loinc("4548-4")


def test_referral_sample():
    path = DOC_SAMPLES / "referral_cardiology.json"
    if not path.exists():
        pytest.skip("referral sample missing")
    out = process_document(path.read_bytes(), filename=path.name, lang="de", mode="offline")
    assert out["document_type"] == "referral"


def test_doctor_letter_sample():
    path = DOC_SAMPLES / "doctor_letter_followup.json"
    if not path.exists():
        pytest.skip("doctor letter sample missing")
    out = process_document(path.read_bytes(), filename=path.name, lang="de", mode="offline")
    assert out["document_type"] == "doctor_letter"
