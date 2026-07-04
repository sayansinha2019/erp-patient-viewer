"""Tests for E-Rezept mock client and translation modes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.erp_client import ErpClient, ErpClientError, extract_prescription_payload
from backend.fhir_parser import load_sample
from backend.humanizer import humanize
from backend.main import app
from backend.translator import translate_humanized

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "api-erp" / "samples" / "qes"
client = TestClient(app)


@pytest.fixture
def sample_xml_path():
    path = SAMPLES_DIR / "f70585e0-82f9-4d3d-b248-94504ccf6a66.xml"
    if not path.exists():
        pytest.skip("api-erp samples not cloned")
    return path


def test_erp_mock_list_tasks():
    resp = client.get("/api/erp/mock/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tasks"]) >= 1
    assert data["mock_token"]


def test_erp_mock_fetch(sample_xml_path, monkeypatch):
    monkeypatch.setenv("ERP_MODE", "mock")
    resp = client.get(
        "/api/erp/fetch/160.100.000.000.016.91?lang=en&mode=offline",
        headers={"Authorization": "Bearer demo-bearer-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"]["prescription_id"] == "160.100.000.000.016.91"
    assert body["erp"]["mode"] == "mock"


def test_erp_mock_wrong_token(monkeypatch):
    monkeypatch.setenv("ERP_MODE", "mock")
    resp = client.get(
        "/api/erp/fetch/160.100.000.000.016.91",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


def test_offline_german_labels(sample_xml_path):
    parsed = load_sample(sample_xml_path)
    humanized = humanize(parsed)
    result = translate_humanized(humanized, "de", parsed=parsed, mode="offline")
    assert result["translation_provider"] == "offline"
    title = result["sections"]["summary"]["title"]
    assert "E-Rezept" in title or "Rezept" in title


def test_erp_client_extract(sample_xml_path):
    raw = sample_xml_path.read_bytes()
    payload, hint = extract_prescription_payload(raw)
    assert b"MedicationRequest" in payload or b"Bundle" in payload


def test_languages_expanded():
    resp = client.get("/api/languages")
    assert resp.status_code == 200
    langs = resp.json()["languages"]
    assert len(langs) >= 40
    assert "ja" in langs
    assert "sw" in langs
