"""Production clinical search (KLARIFY_EMBEDDINGS=local): German/English queries -> right entry.

The model test runs only when the local ONNX model is already on disk (Docker image, or after
`python -m backend.dictionaries.clinical_index --download-model`); tests never download it.
"""

import pytest

from backend.dictionaries import clinical_index as ci

# Calibration set for _LOCAL_MAX_DISTANCE: query -> acceptable top entries (None = must return nothing)
QUERIES = {
    "Zuckerkrankheit": ("ICD-10 E11.9", "ICD-10 E11.65"),
    "Nierenfunktion eingeschränkt": ("ICD-10 N18.3", "LOINC 33914-3"),
    "Blutdruck zu hoch": ("ICD-10 I10",),
    "Bluthochdruck": ("ICD-10 I10",),
    "Schmerzmittel Fieber": ("ATC N02BE01",),
    "Kreatinin": ("LOINC 2160-0",),
    "Langzeitblutzucker": ("LOINC 4548-4",),
    "Cholesterin erhöht": ("ICD-10 E78.5", "LOINC 2093-3"),
    "Schilddrüsenhormon": ("ATC H03AA01",),
    "Sodbrennen": ("ICD-10 K21.9", "ATC A02BC01"),
    "Rückenschmerzen": ("ICD-10 M54.5",),
    "high blood pressure": ("ICD-10 I10",),
    "kidney function": ("ICD-10 N18.3", "LOINC 33914-3"),
    "type 2 diabetes": ("ICD-10 E11.9", "ICD-10 E11.65"),
    "Metformin 1000 mg Filmtabletten": ("ATC A10BA02",),
    "metfromin": ("ATC A10BA02",),
    "L-Thyroxin": ("ATC H03AA01",),
    "Prospan Hustensaft": None,  # not in the dictionary
    "random football weather": None,
}


def test_search_texts_include_german_terms():
    entry = ci._build_lookup()["loinc:2160-0"]
    texts = ci._entry_search_texts(entry)
    assert texts[0] == ci._entry_document(entry)
    assert "Kreatinin" in texts


@pytest.fixture(scope="module")
def local_index(tmp_path_factory):
    model_dir = ci.local_model_dir()
    if not (model_dir / ci.LOCAL_EMBED_FILE).exists():
        pytest.skip(f"local embedding model not downloaded ({model_dir})")
    mp = pytest.MonkeyPatch()
    mp.setenv("KLARIFY_EMBEDDINGS", "local")
    mp.setenv("KLARIFY_LOCAL_MODEL_DIR", str(model_dir))
    mp.setenv("KLARIFY_CACHE_DIR", str(tmp_path_factory.mktemp("cache")))
    mp.setenv("KLARIFY_MODEL_DOWNLOAD", "0")
    mp.delenv("KLARIFY_SEARCH_MAX_DISTANCE", raising=False)
    mp.delenv("KLARIFY_DISABLE_CHROMA", raising=False)
    mp.setattr(ci, "_INDEX", None)
    mp.setattr(ci, "_INDEX_FAILED_AT", None)
    assert ci._get_chroma_index() is not None
    yield
    mp.undo()


@pytest.mark.parametrize("query,expected", list(QUERIES.items()))
def test_local_search_german(local_index, query, expected):
    hits = ci.semantic_search(query)
    if expected is None:
        assert hits == []
    else:
        assert hits and hits[0].startswith(expected), hits
