# E-Rezept Patient Viewer

Demo app that parses [gematik/api-erp](https://github.com/gematik/api-erp) FHIR e-prescription samples and explains them in plain language, with optional translation.

## What this does

1. **Parse** — Reads FHIR Bundle XML/JSON from the api-erp `samples/qes/` folder (or uploads).
2. **Humanize** — Maps technical FHIR codes (PZN, co-payment status, insurance type, etc.) to patient-friendly English.
3. **Translate** — Uses **Google Gemini** (when `GEMINI_API_KEY` is set) for accurate, context-aware translation and a plain-language patient summary. Supports **50+ languages**, **offline mode**, and **disk cache**.

4. **Fetch from E-Rezept** — Mock Fachdienst (default) or live TI with Bearer token.

## Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Key settings:

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Gemini translation (optional but recommended) |
| `TRANSLATION_MODE` | `auto` \| `gemini` \| `offline` \| `online` |
| `ERP_MODE` | `mock` (demo) or `live` (real TI) |
| `ERP_ACCESS_TOKEN` | Bearer token from gematik IDP (live only) |

## How to test

See **[TESTING.md](TESTING.md)** for step-by-step instructions (samples, offline mode, mock Fachdienst, live TI).

## Quick start

```bash
cd erp-patient-viewer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8080
```

Open http://localhost:8080

## Run tests

```bash
pytest tests/ -v
```

## About api-erp

The upstream repo is **API documentation** for Germany's E-Rezept (electronic prescription), not a runnable patient app. This project wraps its **dummy FHIR samples** in a testable pipeline plus a simple UI.

The gematik doc build (`resources/scripts/build_with_replace_includes.sh`) requires Ruby Asciidoctor and is separate from this demo.

## Disclaimer

Demo only — not for clinical or production use.
