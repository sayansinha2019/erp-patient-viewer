"""E-Rezept Fachdienst client — mock (demo) and live (TI Bearer token) modes."""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

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

FHIR_NS = {"f": "http://hl7.org/fhir"}


class ErpClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ErpClient:
    def __init__(self) -> None:
        self.mode = os.getenv("ERP_MODE", "mock").lower()
        self.base_url = os.getenv("ERP_BASE_URL", "https://erp.app.ti-dienste.de").rstrip("/")
        self.access_token = os.getenv("ERP_ACCESS_TOKEN", "")
        self.mock_token = os.getenv("ERP_MOCK_TOKEN", "demo-bearer-token")
        self._task_index: dict[str, Path] | None = None

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "base_url": self.base_url,
            "has_access_token": bool(self.access_token),
            "mock_token_hint": self.mock_token if self.mode == "mock" else None,
            "samples_available": SAMPLES_DIR.exists(),
            "mock_task_count": len(self._build_task_index()),
        }

    def _build_task_index(self) -> dict[str, Path]:
        if self._task_index is not None:
            return self._task_index
        index: dict[str, Path] = {}
        if not SAMPLES_DIR.exists():
            self._task_index = index
            return index
        for path in SAMPLES_DIR.glob("*.xml"):
            try:
                root = ET.parse(path).getroot()
                id_el = root.find("f:identifier/f:value", FHIR_NS)
                bundle_id = root.find("f:id", FHIR_NS)
                if id_el is not None and id_el.get("value"):
                    index[id_el.get("value")] = path
                if bundle_id is not None and bundle_id.get("value"):
                    index[bundle_id.get("value")] = path
                index[path.stem] = path
            except ET.ParseError:
                continue
        self._task_index = index
        return index

    def list_mock_tasks(self) -> list[dict[str, str]]:
        tasks = []
        seen: set[str] = set()
        for task_id, path in sorted(self._build_task_index().items()):
            if "." not in task_id or task_id in seen:
                continue
            seen.add(task_id)
            tasks.append({"task_id": task_id, "source_file": path.name})
        return tasks[:20]

    def _auth_headers(self, token: str | None, access_code: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/fhir+json, application/fhir+xml, application/json, application/xml",
        }
        bearer = token or self.access_token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if access_code:
            headers["X-AccessCode"] = access_code
        return headers

    def _mock_fetch(self, task_id: str) -> bytes:
        index = self._build_task_index()
        path = index.get(task_id)
        if path is None:
            raise ErpClientError(f"Mock task not found: {task_id}. Use GET /api/erp/mock/tasks for IDs.", 404)
        return path.read_bytes()

    def _live_fetch(self, task_id: str, token: str | None, access_code: str | None) -> bytes:
        if not (token or self.access_token):
            raise ErpClientError(
                "Live mode requires ERP_ACCESS_TOKEN (Bearer token from gematik IDP). "
                "Set ERP_MODE=mock for demo testing.",
                401,
            )
        url = f"{self.base_url}/Task/{task_id}"
        try:
            with httpx.Client(timeout=30.0, verify=True) as client:
                resp = client.get(url, headers=self._auth_headers(token, access_code))
        except httpx.RequestError as exc:
            raise ErpClientError(f"Could not reach E-Rezept Fachdienst: {exc}") from exc

        if resp.status_code == 401:
            raise ErpClientError("Unauthorized — invalid or expired ACCESS_TOKEN.", 401)
        if resp.status_code == 403:
            raise ErpClientError("Forbidden — token lacks permission for this Task.", 403)
        if resp.status_code == 404:
            raise ErpClientError(f"Task not found: {task_id}", 404)
        if resp.status_code >= 400:
            raise ErpClientError(f"Fachdienst error {resp.status_code}: {resp.text[:300]}", resp.status_code)

        return resp.content

    def fetch_task_bundle(
        self,
        task_id: str,
        token: str | None = None,
        access_code: str | None = None,
    ) -> tuple[bytes, str]:
        if self.mode == "mock":
            if token and token != self.mock_token:
                raise ErpClientError(
                    f"Mock mode: use Bearer token '{self.mock_token}' (or leave blank).",
                    401,
                )
            content = self._mock_fetch(task_id)
            return content, "mock"

        return self._live_fetch(task_id, token, access_code), "live"

    def check_connectivity(self, token: str | None = None) -> dict[str, Any]:
        if self.mode == "mock":
            return {"ok": True, "mode": "mock", "message": "Mock mode — no live TI connection needed."}

        url = f"{self.base_url}/metadata"
        bearer = token or self.access_token
        if not bearer:
            return {"ok": False, "mode": "live", "message": "No ERP_ACCESS_TOKEN configured."}

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=self._auth_headers(bearer))
            return {
                "ok": resp.status_code == 200,
                "mode": "live",
                "status_code": resp.status_code,
                "message": "CapabilityStatement reachable" if resp.status_code == 200 else resp.text[:200],
            }
        except httpx.RequestError as exc:
            return {"ok": False, "mode": "live", "message": str(exc)}


def extract_prescription_payload(raw: bytes) -> tuple[bytes, str]:
    """
    Extract prescription Bundle from Fachdienst Task response.
    Returns (content, filename_hint).
    """
    text = raw.decode("utf-8", errors="replace").strip()
    if text.startswith("<"):
        return _extract_from_xml(raw)
    return _extract_from_json(raw)


def _extract_from_json(raw: bytes) -> tuple[bytes, str]:
    data = json.loads(raw)
    if data.get("resourceType") == "Bundle":
        for entry in data.get("entry", []):
            res = entry.get("resource", {})
            if res.get("resourceType") == "Bundle" and _has_prescription(res):
                return json.dumps(res, ensure_ascii=False).encode(), "prescription.json"
            if res.get("resourceType") == "Composition" or _entry_has_medication_request(entry):
                return raw, "task_bundle.json"
    return raw, "response.json"


def _extract_from_xml(raw: bytes) -> tuple[bytes, str]:
    root = ET.fromstring(raw)
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if tag != "Bundle":
        return raw, "response.xml"

    for entry in root.findall("f:entry", FHIR_NS):
        resource = entry.find("f:resource", FHIR_NS)
        if resource is None:
            continue
        inner = resource.find("f:Bundle", FHIR_NS)
        if inner is not None and _xml_has_prescription(inner):
            return ET.tostring(inner, encoding="unicode").encode(), "prescription.xml"
        if resource.find("f:MedicationRequest", FHIR_NS) is not None:
            return raw, "task_bundle.xml"
    return raw, "response.xml"


def _has_prescription(bundle: dict) -> bool:
    for entry in bundle.get("entry", []):
        if entry.get("resource", {}).get("resourceType") == "MedicationRequest":
            return True
    return False


def _entry_has_medication_request(entry: dict) -> bool:
    return entry.get("resource", {}).get("resourceType") == "MedicationRequest"


def _xml_has_prescription(bundle: ET.Element) -> bool:
    return bundle.find(".//f:MedicationRequest", FHIR_NS) is not None
