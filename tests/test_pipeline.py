"""Pipeline tests using gematik api-erp sample data."""

from pathlib import Path

import pytest

from backend.fhir_parser import load_sample, parse_fhir
from backend.humanizer import humanize
from backend.translator import translate_humanized

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "api-erp" / "samples" / "qes"


@pytest.fixture
def sample_xml_path():
    path = SAMPLES_DIR / "f70585e0-82f9-4d3d-b248-94504ccf6a66.xml"
    if not path.exists():
        pytest.skip("api-erp samples not cloned")
    return path


def test_parse_sample_prescription(sample_xml_path):
    parsed = load_sample(sample_xml_path)
    assert parsed["prescription_id"] == "160.100.000.000.016.91"
    assert parsed["patient_name"] == "Prof. Dr. Dr. med Eva Kluge"
    assert "L-Thyroxin" in (parsed["medication_name"] or "")
    assert parsed["pzn"] == "02532741"
    assert parsed["insurance_fund"] == "Techniker-Krankenkasse"


def test_humanize_produces_sections(sample_xml_path):
    parsed = load_sample(sample_xml_path)
    result = humanize(parsed)
    assert result["pipeline_status"]["parse_ok"] is True
    assert result["pipeline_status"]["has_medication"] is True
    assert "Your e-prescription at a glance" in result["sections"]["summary"]["title"]
    assert result["sections"]["medication"]["items"]


def test_full_pipeline_english(sample_xml_path):
    parsed = load_sample(sample_xml_path)
    humanized = humanize(parsed)
    translated = translate_humanized(humanized, "en")
    assert translated["translated"] is False
    assert translated["sections"]["patient"]["items"]


def test_translate_to_german(sample_xml_path):
    parsed = load_sample(sample_xml_path)
    humanized = humanize(parsed)
    translated = translate_humanized(humanized, "de", parsed=parsed)
    assert translated["translated"] is True
    title = translated["sections"]["summary"]["title"]
    assert title
    if translated.get("translation_provider") == "gemini":
        assert translated.get("patient_summary")


def test_parse_ingredient_medication(sample_xml_path):
    """Sample 218b581d uses Wirkstoff (active ingredient) not PZN product name."""
    path = sample_xml_path.parent / "218b581d-ccbe-480e-b8d7-f5f9b925e8c4.xml"
    if not path.exists():
        pytest.skip("ingredient sample missing")
    parsed = load_sample(path)
    assert parsed["medication_name"] is not None
    assert "Gabapentin" in parsed["medication_name"]
    assert parsed["pzn"] is None or parsed["pzn"] != "wirkstoff"


def test_all_qes_samples_parse():
    if not SAMPLES_DIR.exists():
        pytest.skip("api-erp samples not cloned")
    xml_files = list(SAMPLES_DIR.glob("*.xml"))
    assert len(xml_files) >= 1
    for path in xml_files[:5]:
        parsed = load_sample(path)
        assert parsed.get("bundle_id") or parsed.get("prescription_id")
