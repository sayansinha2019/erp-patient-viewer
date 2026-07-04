"""E-Rezept patient-friendly viewer API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .chatbot import chat_about_prescription
from .logging_config import get_logger, setup_logging
from .erp_client import ErpClient, ErpClientError, extract_prescription_payload
from .fhir_parser import load_sample, parse_fhir
from .humanizer import humanize
from .languages import SUPPORTED_LANGUAGES
from .translator import translate_humanized

APP_DIR = Path(__file__).resolve().parent.parent


def _samples_dir() -> Path:
    env_path = os.getenv("ERP_SAMPLES_DIR")
    if env_path:
        return Path(env_path)
    local = APP_DIR.parent / "api-erp" / "samples" / "qes"
    bundled = APP_DIR / "data" / "samples"
    if local.exists():
        return local
    return bundled


SAMPLES_DIR = _samples_dir()
STATIC_DIR = APP_DIR / "static"

app = FastAPI(
    title="E-Rezept Patient Viewer",
    description="Parse gematik FHIR e-prescriptions and explain them in plain language.",
    version="0.2.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
setup_logging()
erp = ErpClient()
log = get_logger("api")


def _process(parsed: dict, lang: str, mode: Optional[str] = None) -> dict:
    humanized = humanize(parsed)
    log.info(
        "process prescription=%s lang=%s mode=%s has_medication=%s",
        parsed.get("prescription_id") or parsed.get("bundle_id"),
        lang,
        mode or "auto",
        bool(parsed.get("medication_name")),
    )
    result = translate_humanized(humanized, lang, parsed=parsed, mode=mode)
    section_counts = {k: len(v.get("items", {})) for k, v in result.get("sections", {}).items()}
    log.info(
        "result provider=%s sections=%s has_summary=%s",
        result.get("translation_provider"),
        section_counts,
        bool(result.get("patient_summary")),
    )
    return {"parsed": parsed, "humanized": result}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "samples_dir": str(SAMPLES_DIR),
        "samples_count": len(list(SAMPLES_DIR.glob("*.xml"))) if SAMPLES_DIR.exists() else 0,
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/results")
def results_page():
    return FileResponse(STATIC_DIR / "results.html")


@app.get("/api/languages")
def languages():
    return {
        "languages": SUPPORTED_LANGUAGES,
        "translation_modes": ["auto", "gemini", "offline", "online"],
        "default_mode": os.getenv("TRANSLATION_MODE", "auto"),
    }


@app.get("/api/samples")
def list_samples():
    if not SAMPLES_DIR.exists():
        return {"samples": []}
    files = sorted(SAMPLES_DIR.glob("*.xml"))
    return {
        "samples": [
            {"id": f.stem, "filename": f.name, "label": f"Sample prescription ({f.stem[:8]}…)"}
            for f in files
        ]
    }


@app.get("/api/samples/{sample_id}/raw")
def get_sample_raw(sample_id: str):
    path = SAMPLES_DIR / f"{sample_id}.xml"
    if not path.exists():
        raise HTTPException(404, f"Sample not found: {sample_id}")
    content = path.read_text(encoding="utf-8")
    parsed = load_sample(path)
    return {
        "id": sample_id,
        "filename": path.name,
        "content": content,
        "prescription_id": parsed.get("prescription_id"),
        "medication_name": parsed.get("medication_name"),
        "patient_name": parsed.get("patient_name"),
    }


@app.get("/api/erp/status")
def erp_status():
    client = ErpClient()
    return {"erp": client.status(), "connectivity": client.check_connectivity()}


@app.get("/api/erp/mock/tasks")
def erp_mock_tasks():
    client = ErpClient()
    if client.mode != "mock":
        raise HTTPException(400, "Only available when ERP_MODE=mock")
    return {"tasks": client.list_mock_tasks(), "mock_token": client.mock_token}


@app.get("/api/erp/fetch/{task_id}")
def erp_fetch_task(
    task_id: str,
    lang: str = "en",
    mode: Optional[str] = None,
    access_code: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    client = ErpClient()
    try:
        raw, source = client.fetch_task_bundle(task_id, token=token, access_code=access_code)
        payload, filename = extract_prescription_payload(raw)
        parsed = parse_fhir(payload, filename=filename)
    except ErpClientError as exc:
        raise HTTPException(exc.status_code or 400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Could not parse Fachdienst response: {exc}") from exc

    out = _process(parsed, lang, mode=mode)
    out["erp"] = {"task_id": task_id, "source": source, "mode": client.mode}
    return out


@app.get("/api/process/sample/{sample_id}")
def process_sample(sample_id: str, lang: str = "en", mode: Optional[str] = None):
    path = SAMPLES_DIR / f"{sample_id}.xml"
    if not path.exists():
        raise HTTPException(404, f"Sample not found: {sample_id}")
    parsed = load_sample(path)
    out = _process(parsed, lang, mode=mode)
    out["sample_file"] = path.name
    return out


@app.post("/api/process")
async def process_upload(
    file: UploadFile = File(...),
    lang: str = Form("en"),
    mode: Optional[str] = Form(None),
):
    content = await file.read()
    try:
        parsed = parse_fhir(content, filename=file.filename)
    except Exception as exc:
        log.exception("parse upload failed: %s", file.filename)
        raise HTTPException(400, f"Could not parse FHIR data: {exc}") from exc
    out = _process(parsed, lang, mode=mode)
    out["filename"] = file.filename
    return out


@app.post("/api/process/raw")
async def process_raw(payload: dict):
    content = payload.get("content", "")
    lang = payload.get("lang", "en")
    mode = payload.get("mode")
    filename = payload.get("filename", "upload.xml")
    try:
        parsed = parse_fhir(content, filename=filename)
    except Exception as exc:
        raise HTTPException(400, f"Could not parse FHIR data: {exc}") from exc
    out = _process(parsed, lang, mode=mode)
    out["filename"] = filename
    return out


@app.post("/api/chat")
async def prescription_chat(payload: dict):
    message = payload.get("message", "")
    parsed = payload.get("parsed")
    humanized = payload.get("humanized")
    history = payload.get("history", [])
    lang = payload.get("lang", "en")

    if not parsed or not humanized:
        raise HTTPException(400, "Missing prescription context. Reload the results page.")

    result = chat_about_prescription(
        message=message,
        parsed=parsed,
        humanized=humanized,
        history=history,
        lang=lang,
    )
    return result
