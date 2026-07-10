"""ePA FHIR API client — mock, HAPI local, TITUS sandbox."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from .logging_config import get_logger

log = get_logger("epa")

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples" / "documents"


class EpaClientError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class EpaClient:
    def __init__(self):
        self.mode = os.getenv("EPA_MODE", "mock").lower()
        self.base_url = os.getenv("EPA_FHIR_BASE_URL", "http://localhost:8080/fhir").rstrip("/")
        self.titus_url = os.getenv("EPA_TITUS_URL", "https://epa.ms.gematik-sandbox.de/fhir").rstrip("/")
        self.oauth_url = os.getenv("EPA_OAUTH_URL", "https://idp.gematik-sandbox.de/oauth2")

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "base_url": self.base_url if self.mode == "hapi" else self.titus_url if self.mode == "titus" else "mock",
            "oauth_configured": bool(os.getenv("EPA_CLIENT_ID")),
        }

    def check_connectivity(self) -> dict[str, Any]:
        if self.mode == "mock":
            return {"reachable": True, "detail": "mock mode"}
        url = f"{self.base_url}/metadata" if self.mode == "hapi" else f"{self.titus_url}/metadata"
        try:
            r = httpx.get(url, timeout=5.0)
            return {"reachable": r.status_code < 500, "status_code": r.status_code}
        except Exception as exc:
            return {"reachable": False, "detail": str(exc)}

    def oauth_authorize_url(self, redirect_uri: str, state: str) -> str:
        client_id = os.getenv("EPA_CLIENT_ID", "klarify-dev")
        return (
            f"{self.oauth_url}/authorize?response_type=code&client_id={client_id}"
            f"&redirect_uri={redirect_uri}&state={state}&scope=openid%20epa"
        )

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        if not os.getenv("EPA_CLIENT_SECRET"):
            return {"access_token": "sandbox-demo-token", "token_type": "Bearer", "expires_in": 3600}
        try:
            r = httpx.post(
                f"{self.oauth_url}/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": os.getenv("EPA_CLIENT_ID"),
                    "client_secret": os.getenv("EPA_CLIENT_SECRET"),
                },
                timeout=15.0,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            raise EpaClientError(f"OAuth token exchange failed: {exc}") from exc

    def list_documents(self, patient_id: str, token: str) -> list[dict[str, Any]]:
        if self.mode == "mock":
            return self._mock_documents()
        bundle = self._fetch_everything(patient_id, token)
        return self._bundle_to_document_list(bundle)

    def fetch_document(self, patient_id: str, doc_id: str, token: str) -> bytes:
        if self.mode == "mock":
            for ext in (".json", ".xml"):
                path = SAMPLES_DIR / f"{doc_id}{ext}"
                if path.exists():
                    return path.read_bytes()
            raise EpaClientError(f"Document not found: {doc_id}", 404)
        url = f"{self._api_base()}/{doc_id}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"}
        r = httpx.get(url, headers=headers, timeout=30.0)
        if r.status_code >= 400:
            raise EpaClientError(f"ePA fetch failed: {r.status_code}", r.status_code)
        return r.content

    def _api_base(self) -> str:
        return self.base_url if self.mode == "hapi" else self.titus_url

    def _fetch_everything(self, patient_id: str, token: str) -> dict:
        url = f"{self._api_base()}/Patient/{patient_id}/$everything"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"}
        r = httpx.get(url, headers=headers, timeout=60.0)
        if r.status_code >= 400:
            raise EpaClientError(f"ePA $everything failed: {r.status_code}", r.status_code)
        return r.json()

    def _bundle_to_document_list(self, bundle: dict) -> list[dict[str, Any]]:
        docs = []
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            rtype = res.get("resourceType")
            rid = res.get("id") or entry.get("fullUrl", "").split("/")[-1]
            if rtype in ("Composition", "DiagnosticReport", "MedicationRequest", "ServiceRequest"):
                docs.append({
                    "id": rid,
                    "type": self._resource_to_doc_type(rtype, res),
                    "title": res.get("title") or res.get("code", {}).get("text") or rtype,
                    "date": res.get("date") or res.get("effectiveDateTime") or res.get("authoredOn"),
                })
        return docs

    def _resource_to_doc_type(self, rtype: str, res: dict) -> str:
        if rtype == "MedicationRequest":
            return "prescription"
        if rtype == "DiagnosticReport":
            return "lab_result"
        if rtype == "ServiceRequest":
            return "referral"
        title = (res.get("title") or "").lower()
        if "entlass" in title or "discharge" in title:
            return "discharge"
        return "doctor_letter"

    def _mock_documents(self) -> list[dict[str, Any]]:
        if not SAMPLES_DIR.exists():
            return []
        out = []
        for path in sorted(SAMPLES_DIR.glob("*")):
            if path.suffix not in (".json", ".xml"):
                continue
            stem = path.stem
            doc_type = stem.split("_")[0] if "_" in stem else "prescription"
            if stem.startswith("lab"):
                doc_type = "lab_result"
            elif stem.startswith("discharge"):
                doc_type = "discharge"
            elif stem.startswith("referral"):
                doc_type = "referral"
            elif stem.startswith("doctor"):
                doc_type = "doctor_letter"
            out.append({
                "id": stem,
                "type": doc_type,
                "title": stem.replace("_", " ").title(),
                "date": None,
                "filename": path.name,
            })
        return out
