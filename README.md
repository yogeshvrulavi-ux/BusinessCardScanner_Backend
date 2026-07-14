# CardSync AI — Backend API

Standalone **Python-only** FastAPI service. All integrations (Zoho CRM, OCR, WhatsApp, email, PostgreSQL) run here — there is no Node/Express backend.

The React app in `frontend/` talks to this API over HTTP. Vite dev proxies `/api`, `/contacts`, `/health`, etc. to port 5000. Card OCR runs in the browser, not on this API.

## Structure

```
backend/
  main.py              # FastAPI app + /health
  run.py               # Local dev entry (uvicorn)
  requirements.txt
  config/
    settings.py        # CORS + app metadata
  api/
    schemas.py         # Pydantic request/response models
    outreach.py        # WhatsApp/email scheduling helpers
    routes/
      ocr.py           # (removed — OCR runs in browser)
      contacts.py      # Contact CRUD + Zoho sync
      leads.py         # /api/leads/* (Zoho CRM)
      integrations.py  # WhatsApp/email queues + thank-you
      admin.py         # POST /admin/wipe-all-data
  services/
    zoho_service.py    # Zoho OAuth + leads API
    ocr_service.py     # (removed — OCR runs in browser)
    whatsapp_service.py
    email_service.py
    local_db_service.py  # PostgreSQL (psycopg2, same schema as Prisma)
  utils/
  scripts/
```

## Quick start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Edit .env — Zoho, DATABASE_URL, WhatsApp, email keys
python run.py
```

- API: http://127.0.0.1:5000  
- Swagger: http://127.0.0.1:5000/docs  
- Health: http://127.0.0.1:5000/health  

## Run frontend + backend together

```powershell
cd frontend
npm install
npm run dev:all
```

This starts Python on :5000 and Vite on :5173 with API proxy.

## Zoho CRM

Configure in `.env`:

```
ZOHO_CLIENT_ID=
ZOHO_CLIENT_SECRET=
ZOHO_REFRESH_TOKEN=
ZOHO_API_DOMAIN=https://www.zohoapis.com
```

Endpoints used by the frontend:

| Action | Route |
|--------|-------|
| Create lead | `POST /api/leads/create` |
| Sync from local payload | `POST /api/leads/sync-from-local` |
| Sync stored contact | `POST /contacts/{id}/sync-to-zoho` |
| Sync all pending | `POST /contacts/sync-pending-to-zoho` |
| List leads | `GET /api/leads` |

CLI: `python scripts/sync-one-to-zoho.py [contact_id]`

## PostgreSQL

Set `DATABASE_URL` and `CONTACT_STORAGE=postgresql`. Apply schema once from `main/`:

```powershell
cd main
npm run db:push
```

Contact CRUD is served by Python (`/api/contacts`) — no separate Node local-db server.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/sync_env_from_main.py` | Copy `main/.env` → `backend/.env` |
| `scripts/sync_env_to_frontend.py` | Copy VITE vars → `frontend/.env` |
| `scripts/sync-one-to-zoho.py` | Sync one contact to Zoho manually |
| `scripts/wipe_all_data.py` | Wipe DB + optional Zoho (`npm run wipe:all` from frontend) |
| `scripts/test_email_send.py` | Test email delivery |
| `scripts/test_whatsapp_send.py` | Test WhatsApp delivery |

## Production

- Card OCR runs in the **browser** (Tesseract.js + `/tessdata/eng.traineddata`).
- Backend handles Zoho sync, WhatsApp, email (Brevo), and PostgreSQL when configured.
- Set `FRONTEND_URL` and `ALLOWED_ORIGINS` to your deployed site URL.

## Removed (do not use)

- `main/backend/` — old Express + Node Zoho/OCR stack (deleted)
- `main/server/local-db.ts` — Node Prisma API on :3001 (replaced by Python `/api/contacts`)
