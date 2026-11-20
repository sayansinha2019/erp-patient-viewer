"""Klarify API — full health document pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .chatbot import chat_about_prescription
from .clinical_qa import run_all_qa, validate_output_against_ground_truth
from .epa_client import EpaClient, EpaClientError
from .erp_client import ErpClient, ErpClientError, extract_prescription_payload
from .fhir_parser import load_sample, parse_fhir
from .languages import KLARIFY_LANGUAGES, SUPPORTED_LANGUAGES
from .logging_config import get_logger, setup_logging
from .pipeline import process_document
from .settings import zero_retention_enabled
from . import storage

APP_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_DIR / "static"
DOCUMENT_SAMPLES = APP_DIR / "data" / "samples" / "documents"
MAX_UPLOAD_BYTES = int(os.getenv("KLARIFY_MAX_UPLOAD_MB", "20")) * 1024 * 1024


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

app = FastAPI(title="Klarify", description="Explain German health documents in plain language.", version="1.0.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
setup_logging()
erp = ErpClient()
epa = EpaClient()
log = get_logger("api")


def _page(name: str) -> FileResponse:
    """HTML pages always revalidate so a new deploy is picked up immediately."""
    return FileResponse(STATIC_DIR / name, headers={"Cache-Control": "no-cache"})


def _auth_user(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return storage.user_from_token(token)
    return None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "product": "klarify",
        "version": "1.0.0",
        "pipeline_layers": ["l1_translation", "l2_flagging", "l3_storage", "l4_fhir"],
        "document_types": ["prescription", "lab_result", "discharge", "referral", "doctor_letter", "pdf"],
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GCP_SERVICE_ACCOUNT_KEY") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
        "samples_count": len(list(SAMPLES_DIR.glob("*.xml"))) if SAMPLES_DIR.exists() else 0,
        "epa_mode": epa.mode,
        "zero_retention": zero_retention_enabled(),
    }


@app.get("/")
def language_page():
    return _page("language.html")


@app.get("/home")
def home_page():
    return _page("home.html")


@app.get("/upload")
def upload_page():
    return _page("upload.html")


@app.get("/epa")
def epa_page():
    return _page("epa.html")


@app.get("/account")
def account_page():
    return _page("account.html")


@app.get("/timeline")
def timeline_page():
    return _page("timeline.html")


@app.get("/results")
def results_page():
    return _page("results.html")


@app.get("/api/languages")
def languages():
    return {
        "languages": SUPPORTED_LANGUAGES,
        "klarify_languages": KLARIFY_LANGUAGES,
        "translation_modes": ["auto", "gemini", "offline", "online"],
        "default_mode": os.getenv("TRANSLATION_MODE", "auto"),
        "zero_retention": zero_retention_enabled(),
    }


@app.get("/api/samples")
def list_samples():
    samples = []
    if SAMPLES_DIR.exists():
        for f in sorted(SAMPLES_DIR.glob("*.xml")):
            samples.append({"id": f.stem, "type": "prescription", "filename": f.name, "label": f"Prescription ({f.stem[:8]}…)"})
    if DOCUMENT_SAMPLES.exists():
        for f in sorted(DOCUMENT_SAMPLES.glob("*.json")):
            samples.append({"id": f.stem, "type": f.stem.split("_")[0], "filename": f.name, "label": f.stem.replace("_", " ").title()})
    return {"samples": samples}


@app.get("/api/process/sample/{sample_id}")
def process_sample(sample_id: str, lang: str = "de", mode: Optional[str] = None):
    path = SAMPLES_DIR / f"{sample_id}.xml"
    if not path.exists():
        path = DOCUMENT_SAMPLES / f"{sample_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Sample not found: {sample_id}")
    content = path.read_bytes()
    out = process_document(content, filename=path.name, lang=lang, mode=mode, source="sample")
    out["sample_file"] = path.name
    return out


@app.post("/api/process")
async def process_upload(file: UploadFile = File(...), lang: str = Form("de"), mode: Optional[str] = Form(None)):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    if not content:
        raise HTTPException(400, "The file is empty.")
    try:
        out = process_document(content, filename=file.filename or "upload.xml", lang=lang, mode=mode)
    except Exception as exc:
        log.exception("upload failed: %s", file.filename)
        raise HTTPException(400, f"Could not read this document: {exc}") from exc
    out["filename"] = file.filename
    return out


@app.post("/api/process/raw")
async def process_raw(payload: dict):
    content = payload.get("content", "")
    lang = payload.get("lang", "de")
    mode = payload.get("mode")
    filename = payload.get("filename", "upload.xml")
    try:
        out = process_document(content, filename=filename, lang=lang, mode=mode)
    except Exception as exc:
        log.exception("raw processing failed: %s", filename)
        raise HTTPException(400, f"Could not read this document: {exc}") from exc
    out["filename"] = filename
    return out


# --- ePA (L4) ---
@app.get("/api/epa/status")
def epa_status():
    return {"epa": epa.status(), "connectivity": epa.check_connectivity()}


@app.get("/api/epa/oauth/url")
def epa_oauth_url(redirect_uri: str, state: str = "klarify"):
    return {"authorize_url": epa.oauth_authorize_url(redirect_uri, state)}


@app.post("/api/epa/oauth/token")
def epa_oauth_token(payload: dict):
    try:
        return epa.exchange_code(payload.get("code", ""), payload.get("redirect_uri", ""))
    except EpaClientError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@app.get("/api/epa/documents")
def epa_list_documents(patient_id: str = "demo-patient", authorization: Optional[str] = Header(None)):
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else "sandbox-demo-token"
    try:
        return {"documents": epa.list_documents(patient_id, token)}
    except EpaClientError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@app.get("/api/epa/documents/{doc_id}/process")
def epa_process_document(doc_id: str, lang: str = "de", mode: Optional[str] = None, patient_id: str = "demo-patient", authorization: Optional[str] = Header(None)):
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else "sandbox-demo-token"
    try:
        raw = epa.fetch_document(patient_id, doc_id, token)
        out = process_document(raw, filename=f"{doc_id}.json", lang=lang, mode=mode, source="epa")
        out["epa"] = {"document_id": doc_id, "mode": epa.mode}
        return out
    except EpaClientError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


# --- E-Rezept Fachdienst ---
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
def erp_fetch_task(task_id: str, lang: str = "de", mode: Optional[str] = None, authorization: Optional[str] = Header(None)):
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    client = ErpClient()
    try:
        raw, source = client.fetch_task_bundle(task_id, token=token)
        payload, filename = extract_prescription_payload(raw)
        out = process_document(payload, filename=filename, lang=lang, mode=mode, source=source)
        out["erp"] = {"task_id": task_id, "mode": client.mode}
        return out
    except ErpClientError as exc:
        raise HTTPException(exc.status_code or 400, str(exc)) from exc


# --- L3 Storage ---
@app.post("/api/auth/register")
def auth_register(payload: dict):
    try:
        return storage.register_user(payload.get("email", ""), payload.get("password", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/auth/login")
def auth_login(payload: dict):
    try:
        return storage.login_user(payload.get("email", ""), payload.get("password", ""))
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc


def _require_user(user_id: Optional[str]) -> str:
    if not user_id:
        raise HTTPException(401, "Your session has expired — please log in again.")
    return user_id


@app.post("/api/storage/save")
def save_explanation(payload: dict, user_id: Optional[str] = Depends(_auth_user)):
    user_id = _require_user(user_id)
    record = payload.get("record")
    if not isinstance(record, dict):
        raise HTTPException(400, "Nothing to save.")
    try:
        rid = storage.save_health_record(user_id, payload.get("password", ""), record)
    except storage.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    storage.log_consent(user_id, "storage_opt_in", "1.0")
    return {"record_id": rid}


# Password travels in the POST body (never in the URL / access logs).
@app.post("/api/timeline")
def get_timeline(payload: dict, user_id: Optional[str] = Depends(_auth_user)):
    user_id = _require_user(user_id)
    try:
        return {"timeline": storage.list_timeline(user_id, payload.get("password", ""))}
    except storage.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc


@app.post("/api/trends")
def get_trends(payload: dict, user_id: Optional[str] = Depends(_auth_user)):
    user_id = _require_user(user_id)
    try:
        return {"trends": storage.compute_trends(user_id, payload.get("password", ""))}
    except storage.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc


# --- Clinical QA ---
@app.get("/api/qa/run")
def qa_run():
    return run_all_qa(lambda content, filename, lang, **kw: process_document(content, filename=filename, lang=lang, mode="offline"))


@app.get("/api/qa/validate/{case_id}")
def qa_validate(case_id: str, sample_id: str, lang: str = "de"):
    path = DOCUMENT_SAMPLES / f"{sample_id}.json"
    if not path.exists():
        path = SAMPLES_DIR / f"{sample_id}.xml"
    if not path.exists():
        raise HTTPException(404, "Sample not found")
    out = process_document(path.read_bytes(), filename=path.name, lang=lang, mode="offline")
    return validate_output_against_ground_truth(case_id, out)


@app.post("/api/chat")
async def document_chat(payload: dict):
    parsed = payload.get("parsed")
    humanized = payload.get("humanized")
    if not parsed or not humanized:
        raise HTTPException(400, "Missing document context")
    return chat_about_prescription(
        message=payload.get("message", ""),
        parsed=parsed,
        humanized=humanized,
        history=payload.get("history", []),
        lang=payload.get("lang", "de"),
    )
