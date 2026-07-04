# Deploy E-Rezept Patient Viewer on Coolify

Guide for [Coolify self-hosted installation](https://coolify.io/docs/get-started/installation).

## Prerequisites

1. **A Linux VPS** (Ubuntu 22.04/24.04 LTS recommended) with:
   - 2+ CPU cores, 2+ GB RAM, 30+ GB disk
   - SSH root access
2. **This repo on GitHub/GitLab** (Coolify deploys from Git)
3. **Gemini API key** for translation + chatbot

---

## Part 1 — Install Coolify on your server

SSH into your VPS as root:

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | sudo bash
```

After install, open `http://YOUR_SERVER_IP:8000` and **create your admin account immediately**.

Docs: [Coolify Installation](https://coolify.io/docs/get-started/installation)

---

## Part 2 — Push this project to Git

From your Mac (in the project folder):

```bash
cd "/Users/vismaya/Desktop/AI Startup /erp-patient-viewer"
git init
git add Dockerfile docker-compose.yml requirements-prod.txt backend static .dockerignore .env.example .gitignore COOLIFY.md
git commit -m "Add Docker and Coolify deployment config"
git branch -M main
git remote add origin https://github.com/YOUR_USER/erp-patient-viewer.git
git push -u origin main
```

Do **not** commit `.env` (contains secrets).

---

## Part 3 — Create application in Coolify

1. In Coolify dashboard → **Projects** → **New Project**
2. **+ New Resource** → **Public Repository** (or Private if you use deploy keys)
3. Repository URL: your Git repo
4. Branch: `main`
5. Build pack: **Dockerfile** (Coolify auto-detects `Dockerfile` in root)

### Environment variables (Coolify → Application → Environment)

| Variable | Required | Example |
|----------|----------|---------|
| `GEMINI_API_KEY` | Yes (for translate/chat) | `your-key` |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` |
| `TRANSLATION_MODE` | No | `auto` |
| `ERP_MODE` | No | `mock` |
| `ERP_MOCK_TOKEN` | No | `demo-bearer-token` |
| `PORT` | No | `8000` (Coolify may set this) |
| `ERP_SAMPLES_DIR` | No | `/app/data/samples` (default in image) |

Mark `GEMINI_API_KEY` as **secret**.

### Port / Domain

- **Internal port:** `8000`
- Add a **domain** in Coolify (e.g. `erp.yourdomain.com`) — Coolify handles SSL via Let's Encrypt
- Or use the generated `*.sslip.io` URL for testing

### Health check

- Path: `/health`
- Expected: HTTP 200 with JSON `{"status":"ok",...}`

---

## Part 4 — Deploy

Click **Deploy** in Coolify. Build steps:

1. Clone repo
2. Build Docker image (includes api-erp sample FHIR files)
3. Start container on port 8000

Open your Coolify URL → you should see the E-Rezept Patient Viewer home page.

---

## Test locally before Coolify (optional)

```bash
cd "/Users/vismaya/Desktop/AI Startup /erp-patient-viewer"
docker compose up --build
```

Visit http://localhost:8000 and http://localhost:8000/health

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No samples in dropdown | Check `/health` → `samples_count` should be > 0 |
| Chat/translate fails | Set `GEMINI_API_KEY` in Coolify env |
| Build fails on git clone | Ensure server has outbound internet |
| 502 after deploy | Confirm port mapping is **8000** |

---

## Note on Mac

Coolify itself runs on **Linux servers**, not macOS. Use Docker Compose locally for testing; use a VPS + Coolify for production hosting.
