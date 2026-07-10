"""Tests for Klarify clinical flagging."""

from backend.flagging.prescription import generate_prescription_flags


def test_flag_copayment_advisory():
    flags = generate_prescription_flags({"copayment": "1", "medication_name": "Test"})
    codes = [f["code"] for f in flags]
    assert "copay_required" in codes
    assert any(f["severity"] == "advisory" for f in flags)


def test_flag_cancelled_urgent():
    flags = generate_prescription_flags({"status": "cancelled"})
    assert any(f["severity"] == "urgent" for f in flags)


def test_flag_no_substitution():
    flags = generate_prescription_flags({"substitution_allowed": False, "medication_name": "X"})
    assert any(f["code"] == "no_substitution" for f in flags)
