# Deploy Klarify for free

Klarify is one Docker container (FastAPI + static pages, port from `$PORT`, health check `/health`).
Any host that builds a `Dockerfile` from a Git repo can run it.

## Option 1: Hugging Face Spaces (easiest, free, 16 GB RAM)

1. Create a Space at huggingface.co/new-space → SDK **Docker** → Blank.
2. Add this header to the top of the Space's `README.md`:
   ```yaml
   ---
   title: Klarify
   sdk: docker
   app_port: 8000
   ---
   ```
3. Push this repo to the Space:
   `git remote add space https://huggingface.co/spaces/<user>/klarify` then `git push space main`.
4. Space → Settings → **Variables and secrets** → add as *secrets*:
   `GCP_PROJECT_ID`, `GCP_LOCATION=global`, `GEMINI_MODEL=gemini-3-flash-preview`,
   `GCP_SERVICE_ACCOUNT_KEY` (the whole JSON on one line).
5. Live at `https://<user>-klarify.hf.space`. Sleeps after ~48 h idle, then wakes on visit.

## Option 2: Google Cloud Run (you already have a GCP project)

Scales to zero; the free tier covers light traffic (Gemini calls are billed separately).
```
gcloud run deploy klarify --source . --region europe-west3 --allow-unauthenticated \
  --service-account nemoya@nemoya-494113.iam.gserviceaccount.com \
  --set-env-vars GEMINI_USE_VERTEX=true,GCP_PROJECT_ID=nemoya-494113,GCP_LOCATION=global,GEMINI_MODEL=gemini-3-flash-preview
```
No key in env vars needed: the service runs *as* the service account.

## Option 3: Render (free web service, 512 MB RAM)

New → Web Service → connect the GitHub repo → runtime **Docker** → instance **Free**.
Set the same env vars plus `KLARIFY_DISABLE_CHROMA=true` (saves ~300 MB RAM).
Health check path `/health`. Sleeps after 15 min idle (~50 s cold start).

## Option 4: Always-free VM (persistent data)

Oracle Cloud Always Free VM + Coolify; see `COOLIFY.md`. The only free option where
saved accounts/timelines survive restarts without extra work.

## Important

- **Saved accounts are SQLite on local disk.** On options 1–3 the disk is wiped on every
  restart/redeploy. Explanations work fine; saved timelines don't persist. For real users,
  use option 4 or move storage to a free Postgres (Neon / Supabase).
- Never commit `.env`. Put secrets only in the host's secret settings.
