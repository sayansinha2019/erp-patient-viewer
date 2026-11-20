"""Clinical code dictionaries with optional Chroma vector index."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "clinical"
_INDEX: Any = None
_LOOKUP: dict[str, dict[str, Any]] = {}


def _load_json(name: str) -> dict | list:
    path = DATA_DIR / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_lookup() -> dict[str, dict[str, Any]]:
    global _LOOKUP
    if _LOOKUP:
        return _LOOKUP

    icd = _load_json("icd10_gm.json")
    loinc = _load_json("loinc.json")
    atc = _load_json("atc.json")

    for code, meta in icd.items():
        _LOOKUP[f"icd:{code}"] = {"system": "icd10_gm", "code": code, **meta}
    for code, meta in loinc.items():
        _LOOKUP[f"loinc:{code}"] = {"system": "loinc", "code": code, **meta}
    for code, meta in atc.items():
        _LOOKUP[f"atc:{code}"] = {"system": "atc", "code": code, **meta}

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


def semantic_search(query: str, n: int = 3) -> list[dict[str, Any]]:
    """Vector search via Chroma when available; keyword fallback otherwise."""
    index = _get_chroma_index()
    if index is not None:
        try:
            results = index.query(query_texts=[query], n_results=n)
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            return [{"text": d, **m} for d, m in zip(docs, metas)]
        except Exception:
            pass

    query_l = query.lower()
    hits = []
    for key, entry in _build_lookup().items():
        text = " ".join(
            str(v) for v in entry.values() if isinstance(v, str)
        ).lower()
        if query_l in text or query_l in key.lower():
            hits.append({"text": text, **entry})
    return hits[:n]


def _get_chroma_index():
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    if os.getenv("KLARIFY_DISABLE_CHROMA", "").lower() in ("1", "true"):
        return None
    try:
        import chromadb
        from chromadb.config import Settings

        persist = Path(os.getenv("KLARIFY_CACHE_DIR") or (Path(__file__).resolve().parents[2] / ".cache")) / "chroma"
        persist.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(persist), settings=Settings(anonymized_telemetry=False))
        collection = client.get_or_create_collection("klarify_clinical")

        if collection.count() == 0:
            ids, documents, metadatas = [], [], []
            for key, entry in _build_lookup().items():
                doc = " ".join(str(v) for v in entry.values() if v)
                ids.append(key)
                documents.append(doc)
                metadatas.append({"system": entry.get("system"), "code": entry.get("code")})
            if ids:
                collection.add(ids=ids, documents=documents, metadatas=metadatas)

        _INDEX = collection
        return _INDEX
    except Exception:
        return None
