"""
CardSync AI — FastAPI backend entry point.

Run locally:
  cd backend
  python -m venv .venv
  .venv\\Scripts\\activate
  pip install -r requirements.txt
  python run.py
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from utils.env_loader import load_env

load_env()

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    for name in (
        "httpx",
        "httpcore",
        "uvicorn.access",
        "services",
        "api",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("services.whatsapp_service").setLevel(logging.INFO)


_configure_logging()
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

from api.routes import build_api_router  # noqa: E402
from api.routes.webhook import router as webhook_router  # noqa: E402
from config.settings import (  # noqa: E402
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    CORS_ORIGIN_REGEX,
    get_allowed_origins,
)
from middleware.auth_middleware import AuthMiddleware  # noqa: E402
from services.email_service import email_queue  # noqa: E402
from services.whatsapp_service import whatsapp_queue  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from services.whatsapp_webhook_setup import ensure_waba_webhook_subscription

    await whatsapp_queue.start()
    await email_queue.start()
    try:
        sub = await asyncio.to_thread(ensure_waba_webhook_subscription)
        if not sub.get("subscribed"):
            logger.warning("WhatsApp WABA webhook subscription: %s", sub)
    except Exception as exc:
        logger.warning("WhatsApp WABA webhook subscription check failed: %s", exc)
    yield
    await whatsapp_queue.stop()
    await email_queue.stop()


app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Health", "description": "Service health and connectivity checks"},
        {"name": "Contacts", "description": "Local DB contact CRUD, duplicates, and Zoho sync"},
        {"name": "Leads", "description": "Zoho CRM leads API"},
        {"name": "Integrations", "description": "WhatsApp and email queue integrations"},
        {"name": "Webhooks", "description": "Meta WhatsApp webhook verification and events"},
        {"name": "Admin", "description": "Destructive admin operations (wipe data)"},
    ],
)

allowed_origins = get_allowed_origins()

# Auth runs inside CORS so 401/403 responses still include Access-Control-Allow-Origin.
app.add_middleware(AuthMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(build_api_router())
app.include_router(webhook_router)


@app.get(
    "/",
    tags=["Health"],
    summary="API root",
    description="Lightweight index for Render health probes. Use `/health` for full service status.",
)
def root():
    return {
        "ok": True,
        "service": "cardsync-backend",
        "health": "/health",
        "docs": "/docs",
        "webhook": "/webhook",
    }


@app.head("/", include_in_schema=False)
def root_head():
    return Response(status_code=200)


@app.get(
    "/health",
    tags=["Health"],
    summary="Health check",
    description=(
        "Reports Zoho, email (Brevo/Gmail), WhatsApp, storage, and webhook configuration. "
        "OCR runs in the browser — not on this API."
    ),
)
def health_check():
    from services.contact_storage import check_storage, storage_label
    from services.email_service import (
        GMAIL_USER,
        brevo_sender_email,
        get_email_provider,
        is_brevo_api_configured,
        is_brevo_smtp_configured,
        is_email_configured,
        is_email_test_recipient_configured,
        is_gmail_configured,
    )
    from api.routes.webhook import get_webhook_verify_token
    from services.whatsapp_service import get_whatsapp_config_summary, is_whatsapp_configured
    from services.whatsapp_webhook_setup import get_waba_subscription_status
    from services.zoho_service import refresh_access_token

    zoho_connected = False
    zoho_error = None
    try:
        token_data = refresh_access_token()
        zoho_connected = bool(token_data.get("access_token"))
    except Exception as exc:
        zoho_error = str(exc)

    provider = get_email_provider()
    payload = {
        "ok": True,
        "service": "cardsync-backend",
        "storage": storage_label(),
        "database": check_storage(),
        "ocr": {
            "location": "browser",
            "note": "Card OCR runs on the device (Tesseract.js). Backend receives extracted fields on save/sync.",
        },
        "zoho": {"connected": zoho_connected},
        "email": {
            "configured": is_email_configured(),
            "provider": provider,
            "brevo_api_configured": is_brevo_api_configured(),
            "brevo_smtp_configured": is_brevo_smtp_configured(),
            "gmail_smtp_configured": is_gmail_configured(),
            "test_recipient_env_set": is_email_test_recipient_configured(),
            "from": brevo_sender_email() or GMAIL_USER or None,
        },
        "whatsapp": {
            "configured": is_whatsapp_configured(),
            "webhook_path": "/webhook",
            "verify_token_set": bool(get_webhook_verify_token()),
            **(get_whatsapp_config_summary() if is_whatsapp_configured() else {}),
            "waba_webhook_subscribed": (
                get_waba_subscription_status() if is_whatsapp_configured() else {"subscribed": False}
            ),
        },
    }
    if zoho_error:
        payload["zoho"]["error"] = zoho_error
    return payload
