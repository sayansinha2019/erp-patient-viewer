# Deploy Klarify for free

Klarify is one Docker container (FastAPI + static pages, port from `$PORT`, health check `/health`).
Any host that builds a `Dockerfile` from a Git repo can run it.

## Hugging Face Spaces: not free anymore

Docker Spaces on the free CPU tier now require a Hugging Face PRO subscription
(only static Spaces are free). If you have PRO: create a Docker Space, add
`sdk: docker` and `app_port: 8000` to the README header, push, and add the
GCP variables below as Space secrets.

## Option 2: Google Cloud Run (you already have a GCP project)


Scales to zero; the free tier covers light traffic (Gemini calls are billed separately).
```
gcloud run deploy klarify --source . --region europe-west3 --allow-unauthenticated \
  --service-account nemoya@nemoya-494113.iam.gserviceaccount.com \
  --set-env-vars GEMINI_USE_VERTEX=true,GCP_PROJECT_ID=nemoya-494113,GCP_LOCATION=global,GEMINI_MODEL=gemini-3-flash-preview
```
No key in env vars needed: the service runs *as* the service account.

## Option 1: Render — DEMO deployment (free, 512 MB RAM, no card)

> ⚠ **Demo only, not production.** `render.yaml` sets `KLARIFY_EMBEDDINGS=vertex`:
> ChromaDB is still the vector store, but embeddings come from Google Vertex AI
> (a third party), so medication names / diagnoses used as search queries leave
> the app. For production use `KLARIFY_EMBEDDINGS=local` on a host with ≥1 GB RAM
> (see "Production setup" below).

1. Open `https://render.com/deploy?repo=https://github.com/sayansinha2019/erp-patient-viewer`
   and sign in (GitHub login is fine).
2. Render reads `render.yaml`. It asks for one secret: **GCP_SERVICE_ACCOUNT_KEY** —
   paste the service-account JSON on one line (from `.env`, *without* the surrounding `'` quotes).
3. Click **Apply**. First build takes ~5–8 min. Live at `https://klarify-xxxx.onrender.com`.
4. Check `https://<your-url>/health` → `"clinical_search": {"ready": true, "demo_only": true}`.

Free plan sleeps after 15 min idle; the first visit after that takes ~50 s.
Every push to `main` redeploys automatically.

## Option 3: Always-free VM (persistent data)

Oracle Cloud Always Free VM + Coolify; see `COOLIFY.md`. The only free option where
saved accounts/timelines survive restarts without extra work.

## Production setup (clinical search stays in-house)

Set `KLARIFY_EMBEDDINGS=local` (the default when the variable is unset; `render.yaml` overrides it
to `vertex` for the demo only).

- **Vector store:** ChromaDB, persisted under `$KLARIFY_CACHE_DIR/chroma`, rebuilt automatically
  when the dictionaries or the model change.
- **Embeddings:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (quantized ONNX,
  `onnx/model_quint8_avx2.onnx`), run inside the app with onnxruntime. Handles German and English;
  no torch, no GPU, no external API. Clinical text never leaves the server.
- **Model is baked into the image:** the `Dockerfile` downloads it at *build* time to
  `/app/models/local-embed` (~120 MB) and sets `KLARIFY_MODEL_DOWNLOAD=0` + `HF_HUB_OFFLINE=1`,
  so the running container never downloads anything. If the files are missing it logs an error and
  falls back to keyword lookup instead of reaching out. Build hosts need internet access to
  huggingface.co; runtime hosts don't.
- **RAM:** the production host needs **≥ 1 GB**. Model + index use ~400 MB, the search stack
  ~500 MB in total, the rest of the app (FastAPI, Gemini client, PDF parsing) comes on top. The
  512 MB free Render plan is too small, which is why the demo uses `vertex`.
- **CPU:** the default model file needs AVX2 (any x86-64 server from the last ~10 years). On ARM
  hosts build with `--build-arg LOCAL_EMBED_FILE=onnx/model_qint8_arm64.onnx`.
- **Check:** `/health` → `"clinical_search": {"embeddings": "local", "demo_only": false, "ready": true,
  "embed_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"}`.
- **Accuracy:** each dictionary entry is indexed as several vectors (full entry, each name, each
  German term in `search_terms_de`), so "Kreatinin", "Zuckerkrankheit" or "L-Thyroxin" find the
  English-named LOINC/ATC entries. Cut-offs `_LOCAL_MAX_DISTANCE` (0.38) and `_LOCAL_MAX_GAP` (0.2)
  are calibrated on the queries in `tests/test_clinical_search.py`; re-run them after changing the
  model or the dictionaries. New entries should get German lay terms in `search_terms_de`.

## Important

- **Saved accounts are SQLite on local disk.** On Render and Cloud Run the disk is wiped on every
  restart/redeploy. Explanations work fine; saved timelines don't persist. For real users,
  use option 3 or move storage to a free Postgres (Neon / Supabase).
- Never commit `.env`. Put secrets only in the host's secret settings.
