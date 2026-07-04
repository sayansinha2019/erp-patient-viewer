"""Tests for prescription-scoped chatbot."""

import pytest

from backend.chatbot import OFF_TOPIC_REPLY, chat_about_prescription
from backend.fhir_parser import load_sample
from backend.humanizer import humanize


@pytest.fixture
def prescription_context():
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent.parent / "api-erp" / "samples" / "qes" / "f70585e0-82f9-4d3d-b248-94504ccf6a66.xml"
    if not path.exists():
        pytest.skip("samples not available")
    parsed = load_sample(path)
    humanized = humanize(parsed)
    return parsed, humanized


def test_chat_endpoint_schema():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 400


@pytest.mark.skipif(not __import__("backend.gemini_client", fromlist=["is_available"]).is_available(), reason="no gemini key")
def test_chat_on_topic(prescription_context):
    parsed, humanized = prescription_context
    result = chat_about_prescription(
        "What medication is on my prescription?",
        parsed,
        humanized,
    )
    assert result["available"]
    assert result["on_topic"]
    assert "L-Thyroxin" in result["reply"] or "thyroxin" in result["reply"].lower()


@pytest.mark.skipif(not __import__("backend.gemini_client", fromlist=["is_available"]).is_available(), reason="no gemini key")
def test_chat_off_topic(prescription_context):
    parsed, humanized = prescription_context
    result = chat_about_prescription(
        "What is the weather in Berlin tomorrow?",
        parsed,
        humanized,
    )
    assert result["available"]
    assert result["on_topic"] is False or "only" in result["reply"].lower() or "prescription" in result["reply"].lower()
