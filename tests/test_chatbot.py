"""Tests for document chatbot."""

import pytest

from backend.chatbot import _educational_reply, chat_about_prescription
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


def test_educational_copayment_no_refusal(prescription_context):
    parsed, humanized = prescription_context
    reply = _educational_reply("what does co payment mean?", parsed, humanized, "en")
    assert reply
    assert "co-payment" in reply.lower() or "zuzahlung" in reply.lower()
    assert "only" not in reply.lower() or "insurance" in reply.lower()


def test_educational_appointment_booking():
    reply = _educational_reply("how to book specialist appointment", {}, {}, "en")
    assert reply
    assert "appointment" in reply.lower() or "practice" in reply.lower() or "gp" in reply.lower()


def test_educational_pharmacy():
    reply = _educational_reply("How do I redeem at pharmacy?", {}, {}, "en")
    assert reply
    assert "pharmacy" in reply.lower()


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
def test_chat_copayment_explains(prescription_context):
    parsed, humanized = prescription_context
    result = chat_about_prescription(
        "what does co payment means?",
        parsed,
        humanized,
    )
    assert result["available"]
    assert result["on_topic"]
    assert "co-payment" in result["reply"].lower() or "zuzahlung" in result["reply"].lower()
    assert "does not contain" not in result["reply"].lower()


@pytest.mark.skipif(not __import__("backend.gemini_client", fromlist=["is_available"]).is_available(), reason="no gemini key")
def test_chat_off_topic(prescription_context):
    parsed, humanized = prescription_context
    result = chat_about_prescription(
        "What is the weather in Berlin tomorrow?",
        parsed,
        humanized,
    )
    assert result["available"]
    assert result["on_topic"] is False or "weather" in result["reply"].lower() or "can't" in result["reply"].lower()
