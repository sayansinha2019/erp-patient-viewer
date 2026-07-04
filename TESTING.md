# Testing Guide — E-Rezept Patient Viewer

Demo only. Not for clinical or production use.

## 1. Start the app

```bash
cd "/Users/vismaya/Desktop/AI Startup /erp-patient-viewer"
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8080
```

Open **http://localhost:8080**

---

## 2. Automated tests

```bash
pytest tests/ -v
```

Covers FHIR parsing, humanization, translation modes, and mock E-Rezept fetch.

---

## 3. Test dummy samples (no network)

### UI
1. Pick a sample from the dropdown.
2. Choose language (e.g. German, Turkish, Arabic).
3. Click **Load sample & translate**.

### API
```bash
curl "http://localhost:8080/api/process/sample/f70585e0-82f9-4d3d-b248-94504ccf6a66?lang=de"
```

Expected: JSON with `parsed.patient_name`, `humanized.sections`, optional `patient_summary`.

---

## 4. Test translation modes

Set in `.env` or pass `?mode=` on API calls.

| Mode | Behavior |
|------|----------|
| `auto` | Gemini → disk cache → offline labels → online fallback |
| `gemini` | Gemini only (needs `GEMINI_API_KEY`) |
| `offline` | Pre-built labels + cached translations (no API calls) |
| `online` | Google Translate fallback |

### Offline test (no Gemini calls)
```bash
curl "http://localhost:8080/api/process/sample/f70585e0-82f9-4d3d-b248-94504ccf6a66?lang=de&mode=offline"
```

Labels should be in German; values stay English unless previously cached.

### Cache test
1. Run once with `mode=gemini` (or `auto` with API key).
2. Run again with `mode=offline` — should return `"translation_provider": "cache"`.

---

## 5. Test mock E-Rezept Fachdienst (live pipeline without TI)

Default: `ERP_MODE=mock` in `.env`.

### List mock task IDs
```bash
curl http://localhost:8080/api/erp/mock/tasks
```

Example task ID: `160.100.000.000.016.91`

### Fetch via mock Fachdienst
```bash
curl -H "Authorization: Bearer demo-bearer-token" \
  "http://localhost:8080/api/erp/fetch/160.100.000.000.016.91?lang=tr&mode=auto"
```

Expected:
- `erp.mode`: `"mock"`
- `erp.source`: `"mock"`
- Full parsed + translated prescription

### UI
1. Open **Fetch from E-Rezept** panel.
2. Task ID: `160.100.000.000.016.91`
3. Token: `demo-bearer-token` (pre-filled in mock mode)
4. Click **Fetch & translate**.

---

## 6. Test live E-Rezept (real TI — advanced)

Requires access to gematik **Referenzumgebung (RU)** or production TI:

1. Set in `.env`:
   ```env
   ERP_MODE=live
   ERP_BASE_URL=https://erp.app.ti-dienste.de
   ERP_ACCESS_TOKEN=<ACCESS_TOKEN from IDP>
   ```

2. Obtain `ACCESS_TOKEN` via gematik IDP OAuth (role: Versicherter). See [api-erp authentisieren](https://github.com/gematik/api-erp/blob/master/docs/authentisieren.adoc).

3. Check connectivity:
   ```bash
   curl http://localhost:8080/api/erp/status
   ```

4. Fetch your Task:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     "http://localhost:8080/api/erp/fetch/160.000.000.000.000.01?lang=en"
   ```

   Optional header for third-party access: `X-AccessCode` (query param `access_code=` in our API).

**Note:** Live TI needs VPN/DNS resolution to `erp.app.ti-dienste.de` and valid certificates. Most developers use **mock mode** for pipeline testing.

---

## 7. Test upload / paste

### Upload FHIR file
```bash
curl -F "file=@../api-erp/samples/qes/f70585e0-82f9-4d3d-b248-94504ccf6a66.xml" \
     -F "lang=fr" \
     -F "mode=auto" \
     http://localhost:8080/api/process
```

### Paste raw FHIR
```bash
curl -X POST http://localhost:8080/api/process/raw \
  -H "Content-Type: application/json" \
  -d '{"content":"<Bundle...","lang":"hi","mode":"offline"}'
```

---

## 8. Languages supported

50+ languages in the UI dropdown. Offline label packs ship for: **de, fr, tr, ar, hi**. All others use Gemini (online) or cache.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Port 8080 in use | `lsof -i :8080` then kill process, or use `--port 8081` |
| Gemini fails | Check `GEMINI_API_KEY` in `.env`; try `mode=offline` |
| Mock 401 | Use token `demo-bearer-token` |
| Mock 404 | Use task ID from `/api/erp/mock/tasks` |
| Live 401 | Refresh `ERP_ACCESS_TOKEN` from IDP |
