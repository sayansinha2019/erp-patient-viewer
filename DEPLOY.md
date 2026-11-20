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
> (and a multilingual local model — the bundled English model handles German poorly).

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

## Important

- **Saved accounts are SQLite on local disk.** On Render and Cloud Run the disk is wiped on every
  restart/redeploy. Explanations work fine; saved timelines don't persist. For real users,
  use option 3 or move storage to a free Postgres (Neon / Supabase).
- Never commit `.env`. Put secrets only in the host's secret settings.
