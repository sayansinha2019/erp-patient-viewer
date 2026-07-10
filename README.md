# Klarify — full health document pipeline

Explain German health documents (e-prescriptions, lab results, discharge letters, referrals, doctor letters, PDFs) in plain language.

## Pipeline layers

| Layer | Module | Capability |
|-------|--------|------------|
| **L4** | `document_router`, `parsers/*`, `epa_client`, `pdf_ingest` | FHIR + PDF ingest, ePA mock/HAPI/TITUS |
| **L1** | `rag_engine`, `dictionaries/clinical_index`, `translator` | RAG + ICD-10/LOINC/ATC + Chroma + Gemini |
| **L2** | `flagging/*` | LOINC ranges, drug interactions, follow-up detection |
| **L3** | `storage` | Accounts, AES-256 encrypted timeline, trends, consent log |
| **QA** | `clinical_qa` | Ground-truth validation suite |

## Document types

- `prescription` — E-Rezept (gematik samples)
- `lab_result` — DiagnosticReport + Observation
- `discharge` — Entlassbrief (Composition)
- `referral` — Überweisung (ServiceRequest)
- `doctor_letter` — Arztbrief (Composition)
- `pdf` — PyMuPDF + optional OCR

## Screens

| Route | Purpose |
|-------|---------|
| `/` | Language selection |
| `/home` | Upload or connect ePA |
| `/upload` | File upload + consent (PDF/FHIR) |
| `/epa` | ePA document browser (sandbox) |
| `/account` | Register / login |
| `/timeline` | Saved health history + lab trends |
| `/results` | Explanation + flags + chat |

## Quick start

```bash
cd erp-patient-viewer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload --port 8080
```

## Clinical QA

```bash
pytest tests/ -v
curl http://localhost:8080/api/qa/run
```

## Configuration

See `.env.example` for `GEMINI_API_KEY`, `EPA_MODE`, `KLARIFY_ZERO_RETENTION`, etc.

**HAPI FHIR local:** `EPA_MODE=hapi` + `docker run -p 8080:8080 hapiproject/hapi:latest`

Disclaimer: Informational demo — not for clinical use.
