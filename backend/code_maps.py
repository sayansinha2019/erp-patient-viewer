"""Human-readable labels and code translations for German e-prescription (E-Rezept) FHIR values."""

LEGAL_BASIS = {
    "00": "Standard prescription (statutory health insurance)",
    "01": "Private prescription",
    "02": "Self-pay prescription",
}

FORM_TYPE = {
    "e16A": "Electronic prescription (e-prescription)",
    "e16B": "Private electronic prescription",
}

COPAYMENT_STATUS = {
    "0": "No co-payment required",
    "1": "Co-payment required",
    "2": "Co-payment exempt due to chronic condition",
    "3": "Co-payment exempt (other reason)",
}

MEDICATION_CATEGORY = {
    "00": "Pharmaceutical product (PZN)",
    "01": "Active ingredient prescription",
    "02": "Free-text prescription",
    "03": "Medical device",
}

DOSAGE_FORM = {
    "TAB": "Tablets",
    "KAP": "Capsules",
    "FTA": "Effervescent tablets",
    "GEL": "Gel",
    "SAL": "Ointment",
    "SOL": "Solution",
    "SUS": "Suspension",
    "SPR": "Spray",
    "ZAM": "Chewable tablets",
    "INF": "Infusion solution",
}

INSURANCE_TYPE = {
    "GKV": "Statutory health insurance",
    "PKV": "Private health insurance",
    "BG": "Occupational accident insurance",
    "SEL": "Self-pay",
}

PRESCRIPTION_STATUS = {
    "active": "Active – ready to be dispensed at a pharmacy",
    "completed": "Already dispensed",
    "cancelled": "Cancelled by prescriber",
    "on-hold": "On hold",
    "stopped": "Stopped",
    "draft": "Draft (not yet issued)",
}

FIELD_LABELS = {
    "prescription_id": "Prescription ID",
    "document_title": "Document type",
    "prescription_date": "Prescribed on",
    "status": "Status",
    "patient_name": "Patient",
    "patient_birth_date": "Date of birth",
    "patient_address": "Patient address",
    "insurance_id": "Insurance card number",
    "insurance_fund": "Health insurance fund",
    "insurance_type": "Insurance type",
    "prescriber_name": "Prescribing doctor",
    "prescriber_specialty": "Medical specialty",
    "practice_name": "Medical practice",
    "practice_address": "Practice address",
    "practice_phone": "Practice phone",
    "medication_name": "Medication",
    "pzn": "Pharmacy product number (PZN)",
    "dosage_form": "Dosage form",
    "quantity": "Quantity",
    "substitution_allowed": "Generic substitution allowed",
    "copayment": "Co-payment status",
    "multiple_prescription": "Repeat prescription",
    "multiple_prescription_number": "Repeat prescription number",
    "multiple_prescription_period": "Repeat prescription period",
    "legal_basis": "Prescription type",
    "form_type": "Form type",
}
