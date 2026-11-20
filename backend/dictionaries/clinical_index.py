"""Clinical code dictionaries + ChromaDB retrieval for RAG.

ChromaDB is always the vector store. Where the embeddings come from is set by
KLARIFY_EMBEDDINGS:

- "local"  (default, PRODUCTION): Chroma's bundled ONNX model runs inside the app.
           Clinical text never leaves our server. Needs ~300 MB+ RAM.
- "vertex" (DEMO ONLY — NOT FOR PRODUCTION): embeddings are computed by Google
           Vertex AI (third party). Query text — which can contain medication
           names / diagnoses from a patient's document — is sent to Google.
           Used only so the demo fits small free hosts (e.g. Render 512 MB).
"""

from __future__ import annotations

import json
import os
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..logging_config import get_logger

log = get_logger("clinical_index")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "clinical"
_INDEX: Any = None
_INDEX_LOCK = threading.Lock()
_INDEX_FAILED_AT: float | None = None
_RETRY_AFTER_S = 60
_LOOKUP: dict[str, dict[str, Any]] = {}

# Cosine distance above this = not relevant enough to put into the prompt.
# Calibrated per model on German/English test queries (gap between the worst correct
# hit and the best off-topic / not-in-dictionary query).
_MAX_DISTANCE_BY_MODEL = {
    "gemini-embedding-001": 0.35,             # correct <= 0.31, irrelevant >= 0.39
    "gemini-embedding-2": 0.375,              # correct <= 0.37, irrelevant >= 0.39
    "text-multilingual-embedding-002": 0.50,  # correct <= 0.47, irrelevant >= 0.56
}
_LOCAL_MAX_DISTANCE = 0.55


def _max_distance() -> float:
    if os.getenv("KLARIFY_SEARCH_MAX_DISTANCE"):
        return float(os.environ["KLARIFY_SEARCH_MAX_DISTANCE"])
    if embeddings_mode() == "vertex":
        return _MAX_DISTANCE_BY_MODEL.get((_EMBED_CHOICE or ("",))[0], 0.4)
    return _LOCAL_MAX_DISTANCE
VERTEX_EMBED_DIMS = int(os.getenv("KLARIFY_EMBED_DIMS", "768"))
# Model availability differs per Google region (requests from some hosts get routed
# elsewhere), so try a chain of models and locations; the first working pair is pinned.
_EMBED_MODELS = list(dict.fromkeys(
    [os.getenv("KLARIFY_EMBED_MODEL", "gemini-embedding-001"), "gemini-embedding-2", "text-multilingual-embedding-002"]
))
_EMBED_LOCATIONS = list(dict.fromkeys(
    [os.getenv("GCP_LOCATION", "global"), "global", "us-central1", "europe-west4"]
))
_EMBED_CHOICE: tuple[str, str] | None = None  # (model, location) used to build the index
_EMBED_CLIENTS: dict[str, Any] = {}


def _load_json(name: str) -> dict | list:
    path = DATA_DIR / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _rename_system(meta: dict[str, Any]) -> dict[str, Any]:
    """Keep a dictionary's own "system" field (e.g. LOINC specimen "Blood") under another key,
    so it can't overwrite the code-system tag."""
    if "system" in meta:
        specimen = meta.get("specimen") or meta["system"]
        meta = {k: v for k, v in meta.items() if k != "system"}
        meta["specimen"] = specimen
    return meta


def _build_lookup() -> dict[str, dict[str, Any]]:
    global _LOOKUP
    if _LOOKUP:
        return _LOOKUP

    icd = _load_json("icd10_gm.json")
    loinc = _load_json("loinc.json")
    atc = _load_json("atc.json")

    for code, meta in icd.items():
        _LOOKUP[f"icd:{code}"] = {**_rename_system(meta), "system": "icd10_gm", "code": code}
    for code, meta in loinc.items():
        _LOOKUP[f"loinc:{code}"] = {**_rename_system(meta), "system": "loinc", "code": code}
    for code, meta in atc.items():
        _LOOKUP[f"atc:{code}"] = {**_rename_system(meta), "system": "atc", "code": code}

    return _LOOKUP


def resolve_icd10(code: str, lang: str = "de") -> str | None:
    entry = _build_lookup().get(f"icd:{code}")
    if not entry:
        return None
    return entry.get(lang) or entry.get("de") or entry.get("en")


def resolve_loinc(code: str) -> dict[str, Any] | None:
    return _build_lookup().get(f"loinc:{code}")


def resolve_atc(code: str) -> dict[str, Any] | None:
    return _build_lookup().get(f"atc:{code}")


_SYSTEM_LABEL = {"icd10_gm": "ICD-10", "loinc": "LOINC", "atc": "ATC"}
_TEXT_FIELDS = ("name", "en", "de", "component", "class", "category", "specimen", "route", "unit")


def _entry_document(entry: dict[str, Any]) -> str:
    """Text that gets embedded for one dictionary entry."""
    label = _SYSTEM_LABEL.get(entry.get("system", ""), "")
    fields = [str(entry[f]) for f in _TEXT_FIELDS if entry.get(f)]
    return f"{label} {entry.get('code', '')}: " + "; ".join(fields)


def format_entry(entry: dict[str, Any]) -> str:
    """Prompt-ready line, e.g. 'ATC A10BA02: Metformin (Antidiabetic, oral)'."""
    label = _SYSTEM_LABEL.get(entry.get("system", ""), entry.get("system", ""))
    name = entry.get("name") or entry.get("en") or entry.get("de") or ""
    extras = [str(entry[f]) for f in ("component", "class", "category", "route") if entry.get(f) and entry.get(f) != name]
    if entry.get("de") and entry.get("de") != name:
        extras.insert(0, entry["de"])
    tail = f" ({', '.join(extras)})" if extras else ""
    return f"{label} {entry.get('code', '')}: {name}{tail}".strip()


# ---------------------------------------------------------------- embeddings

def embeddings_mode() -> str:
    mode = os.getenv("KLARIFY_EMBEDDINGS", "local").lower()
    return mode if mode in ("local", "vertex") else "local"


def _embed_client(location: str):
    """Vertex client for a given location, reusing the app's credentials."""
    if location not in _EMBED_CLIENTS:
        from google import genai

        from ..gemini_client import _get_client, _service_account_info

        base = _get_client()
        if base is None:
            raise RuntimeError("Vertex AI / Gemini client is not configured")
        info = _service_account_info()
        project = os.getenv("GCP_PROJECT_ID") or (info or {}).get("project_id")
        creds = None
        if info:
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        _EMBED_CLIENTS[location] = genai.Client(vertexai=True, project=project, location=location, credentials=creds)
    return _EMBED_CLIENTS[location]


def _embed_with(model: str, location: str, texts: list[str], task_type: str) -> list[list[float]]:
    from google.genai import types

    client = _embed_client(location)
    config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=VERTEX_EMBED_DIMS)
    out: list[list[float]] = []
    for i in range(0, len(texts), 100):  # API batch limit
        batch = texts[i:i + 100]
        resp = client.models.embed_content(model=model, contents=batch, config=config)
        if len(resp.embeddings) == len(batch):
            out.extend(list(e.values) for e in resp.embeddings)
        else:
            # Some models (e.g. gemini-embedding-2) merge a list into ONE vector — embed individually
            for text in batch:
                one = client.models.embed_content(model=model, contents=text, config=config)
                out.append(list(one.embeddings[0].values))
    if len(out) != len(texts):
        raise RuntimeError(f"{model} returned {len(out)} vectors for {len(texts)} texts")
    return out


def _vertex_embed(texts: list[str], task_type: str) -> list[list[float]]:
    """DEMO ONLY: embeddings from Google Vertex AI (text leaves the app).

    The first call picks a working (model, location) pair; later calls reuse it so
    index and query vectors always come from the same model.
    """
    global _EMBED_CHOICE
    if _EMBED_CHOICE:
        return _embed_with(*_EMBED_CHOICE, texts, task_type)
    errors = []
    for model in _EMBED_MODELS:
        for location in _EMBED_LOCATIONS:
            try:
                vectors = _embed_with(model, location, texts, task_type)
                _EMBED_CHOICE = (model, location)
                log.info("Vertex embeddings: using %s @ %s", model, location)
                return vectors
            except Exception as exc:  # 404 = not served in that region, try next
                errors.append(f"{model}@{location}: {str(exc)[:80]}")
    raise RuntimeError("No Vertex embedding model available: " + " | ".join(errors))


@lru_cache(maxsize=512)
def _vertex_query_embedding(text: str) -> tuple[float, ...]:
    return tuple(_vertex_embed([text], "RETRIEVAL_QUERY")[0])


# ---------------------------------------------------------------- Chroma index

def _collection_name() -> str:
    if embeddings_mode() == "vertex":
        model = (_EMBED_CHOICE or (_EMBED_MODELS[0], ""))[0]
        return f"klarify_clinical_vertex_{model.replace('.', '-')}_{VERTEX_EMBED_DIMS}"
    return "klarify_clinical_local"


def _get_chroma_index():
    """Build (once) and return the Chroma collection, or None if unavailable."""
    global _INDEX, _INDEX_FAILED_AT
    if _INDEX is not None or _recently_failed():
        return _INDEX
    if os.getenv("KLARIFY_DISABLE_CHROMA", "").lower() in ("1", "true"):
        return None
    with _INDEX_LOCK:
        if _INDEX is not None or _recently_failed():
            return _INDEX
        try:
            import chromadb
            from chromadb.config import Settings

            persist = Path(os.getenv("KLARIFY_CACHE_DIR") or (Path(__file__).resolve().parents[2] / ".cache")) / "chroma"
            persist.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(persist), settings=Settings(anonymized_telemetry=False))
            mode = embeddings_mode()
            lookup = _build_lookup()
            if mode == "vertex":
                _vertex_embed(["warm-up"], "RETRIEVAL_DOCUMENT")  # pins a working model before naming the collection
            kwargs: dict[str, Any] = {"metadata": {"hnsw:space": "cosine"}}
            if mode == "vertex":
                kwargs["embedding_function"] = None  # we pass vectors ourselves; no local model is loaded
            collection = client.get_or_create_collection(_collection_name(), **kwargs)

            if collection.count() != len(lookup):  # first run or dictionaries changed
                client.delete_collection(_collection_name())
                collection = client.get_or_create_collection(_collection_name(), **kwargs)
                ids = list(lookup)
                documents = [_entry_document(lookup[k]) for k in ids]
                metadatas = [{"system": lookup[k]["system"], "code": lookup[k]["code"]} for k in ids]
                if ids:
                    if mode == "vertex":
                        vectors = _vertex_embed(documents, "RETRIEVAL_DOCUMENT")
                        collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=vectors)
                    else:
                        collection.add(ids=ids, documents=documents, metadatas=metadatas)

            if mode == "vertex":
                log.warning(
                    "DEMO MODE: clinical search embeddings via Google Vertex AI (%s @ %s). "
                    "Query text leaves the app — not for production.", *(_EMBED_CHOICE or ("?", "?")),
                )
            log.info("Chroma clinical index ready (%d entries, embeddings=%s)", collection.count(), mode)
            _INDEX = collection
            _INDEX_FAILED_AT = None
        except Exception:
            log.exception("Chroma clinical index unavailable — keyword lookup for now, retrying in %ss", _RETRY_AFTER_S)
            _INDEX_FAILED_AT = time.monotonic()
    return _INDEX


def _recently_failed() -> bool:
    return _INDEX_FAILED_AT is not None and time.monotonic() - _INDEX_FAILED_AT < _RETRY_AFTER_S


def index_status() -> dict[str, Any]:
    model, location = _EMBED_CHOICE or (None, None)
    return {
        "ready": _INDEX is not None,
        "embed_model": model if embeddings_mode() == "vertex" else "chroma-default-onnx",
        "embed_location": location,
        "last_error": "build failed, retrying" if _INDEX_FAILED_AT is not None else None,
    }


def warm_index() -> None:
    """Build the index in the background at startup so the first user doesn't wait."""
    threading.Thread(target=_get_chroma_index, name="chroma-warmup", daemon=True).start()


def _keyword_fallback(query: str, n: int) -> list[str]:
    """Last resort when Chroma is down: plain substring match."""
    q = query.lower()
    hits = []
    for entry in _build_lookup().values():
        name = str(entry.get("name") or entry.get("en") or "").lower()
        if name and (name in q or q in _entry_document(entry).lower()):
            hits.append(format_entry(entry))
    return hits[:n]


def semantic_search(query: str, n: int = 3) -> list[str]:
    """Most relevant clinical dictionary entries for `query`, as prompt-ready lines."""
    query = (query or "").strip()[:500]
    if not query:
        return []
    index = _get_chroma_index()
    if index is not None:
        try:
            if embeddings_mode() == "vertex":
                results = index.query(query_embeddings=[list(_vertex_query_embedding(query))], n_results=n)
            else:
                results = index.query(query_texts=[query], n_results=n)
            lookup = _build_lookup()
            max_distance = _max_distance()
            ids = results.get("ids", [[]])[0]
            dists = (results.get("distances") or [[None] * len(ids)])[0]
            return [
                format_entry(lookup[i]) for i, d in zip(ids, dists)
                if i in lookup and (d is None or d <= max_distance)
            ]
        except Exception:
            log.exception("Chroma query failed — using keyword lookup")
    return _keyword_fallback(query, n)
