"""Google Sheets secondary sync — mirrors saved contacts into a spreadsheet.

PostgreSQL remains the single source of truth. After a contact row is
committed, the same record is upserted (update-by-Contact-ID, else append)
into a configured Google Sheet for reporting/sharing.

Configuration (environment variables only — nothing hardcoded):
    GOOGLE_SHEET_ID              Spreadsheet ID (from the sheet URL).
    GOOGLE_SHEET_NAME            Tab name (default: "Contacts").
    GOOGLE_SERVICE_ACCOUNT_JSON  Service-account credentials: either the raw
                                 JSON string or a path to the JSON key file.

Behaviour:
    * Runs fire-and-forget in a worker thread — never blocks or fails a save.
    * Update-by-ID is preferred; append only when the Contact ID is not found,
      so no duplicate rows are created for edits or re-syncs.
    * Failures are logged and queued in-process; the next successful sync
      drains the retry queue. A restart clears pending retries (PostgreSQL
      still has the data — re-saving/editing the contact re-syncs it).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from typing import Any

import jwt
import requests

logger = logging.getLogger(__name__)

_SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

# Column layout — order defines the sheet. Keep header text stable.
HEADERS: list[str] = [
    # Contact information
    "Contact ID",
    "Full Name",
    "Company",
    "Designation",
    "Primary Phone",
    "Secondary Phone",
    "Primary Email",
    "Secondary Email",
    "Website",
    "Primary Address",
    "Secondary Address",
    "Notes",
    # Business information
    "Event Name",
    "Company ID",
    "Company Name",
    "Created By",
    "Created By Role",
    "Created Date",
    "Updated Date",
    # OCR information
    "OCR Engine",
    "OCR Confidence",
    "Capture Source",
    # Image information
    "Original Image URL",
    "Image File Name",
    # Application information
    "Contact Status",
    "Scan Status",
    "Created Timestamp",
    "Updated Timestamp",
]

_MAX_ATTEMPTS = 3
_RETRY_DELAYS = (1, 3)  # seconds between attempts

# In-process retry queue: contact ids whose sheet sync failed.
_pending_lock = threading.Lock()
_pending_retry: dict[str, dict[str, Any]] = {}

# Cached access token (service-account tokens last ~1 hour).
_token_lock = threading.Lock()
_cached_token: dict[str, Any] = {"token": None, "expires_at": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

def _sheet_id() -> str:
    return os.getenv("GOOGLE_SHEET_ID", "").strip()


def _sheet_name() -> str:
    return os.getenv("GOOGLE_SHEET_NAME", "").strip() or "Contacts"


def _load_service_account() -> dict[str, Any] | None:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None
    try:
        if raw.startswith("{"):
            return json.loads(raw)
        if os.path.isfile(raw):
            with open(raw, encoding="utf-8") as handle:
                return json.load(handle)
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON is neither JSON nor an existing file path.")
    except Exception as exc:
        logger.warning("Could not load Google service account credentials: %s", exc)
    return None


def is_sheets_configured() -> bool:
    return bool(_sheet_id() and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip())


# ─────────────────────────────────────────────────────────────────────────────
# Auth (service-account JWT → OAuth token; PyJWT signs RS256)
# ─────────────────────────────────────────────────────────────────────────────

def _get_access_token() -> str | None:
    with _token_lock:
        if _cached_token["token"] and time.time() < _cached_token["expires_at"] - 60:
            return _cached_token["token"]

    creds = _load_service_account()
    if not creds:
        return None

    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": creds.get("client_email"),
            "scope": _SCOPE,
            "aud": _TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        },
        creds.get("private_key"),
        algorithm="RS256",
    )
    response = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    with _token_lock:
        _cached_token["token"] = token
        _cached_token["expires_at"] = time.time() + int(payload.get("expires_in", 3600))
    return token


def _auth_headers() -> dict[str, str] | None:
    token = _get_access_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Row building
# ─────────────────────────────────────────────────────────────────────────────

def _column_letter(index: int) -> str:
    """1-based column index → A1 letter (1 → A, 27 → AA)."""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


_LAST_COL = _column_letter(len(HEADERS))


def _card_image_url(contact: dict[str, Any]) -> str:
    if not contact.get("cardImageBase64"):
        return ""
    from config.urls import try_backend_base_url

    base = try_backend_base_url()
    if not base:
        return ""
    return f"{base}/api/contacts/{contact.get('id')}/card-image"


def _image_file_name(contact: dict[str, Any]) -> str:
    data_url = str(contact.get("cardImageBase64") or "")
    if not data_url:
        return ""
    ext = "png" if "image/png" in data_url[:40] else "jpg"
    return f"card-{contact.get('id')}.{ext}"


def contact_to_row(contact: dict[str, Any], extras: dict[str, Any] | None = None) -> list[str]:
    """Map the existing contact model (from `_row_to_contact`) to sheet columns."""
    extras = extras or {}
    created = str(contact.get("created_at") or "")
    updated = str(contact.get("updatedAt") or "")
    confidence = extras.get("ocrConfidence")
    confidence_str = f"{float(confidence):.2f}" if confidence not in (None, "") else ""

    return [
        str(contact.get("id") or ""),
        str(contact.get("fullName") or contact.get("name") or ""),
        str(contact.get("company") or ""),
        str(contact.get("designation") or ""),
        str(contact.get("phone") or ""),
        str(contact.get("secondaryPhone") or ""),
        str(contact.get("email") or ""),
        str(contact.get("secondaryEmail") or ""),
        str(contact.get("website") or ""),
        str(contact.get("address") or ""),
        str(contact.get("secondaryAddress") or ""),
        str(contact.get("notes") or ""),
        str(contact.get("eventName") or ""),
        str(contact.get("owner_company_id") or contact.get("company_id") or ""),
        str(contact.get("admin_name") or ""),
        str(contact.get("user_name") or ""),
        str(contact.get("created_by_role") or ""),
        created[:10],
        updated[:10],
        str(extras.get("ocrEngine") or ""),
        confidence_str,
        str(extras.get("captureSource") or ""),
        _card_image_url(contact),
        _image_file_name(contact),
        str(contact.get("status") or ""),
        str(contact.get("syncStatus") or ""),
        created,
        updated,
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Sheets API helpers
# ─────────────────────────────────────────────────────────────────────────────

def _values_get(headers: dict[str, str], range_: str) -> list[list[str]]:
    url = f"{_SHEETS_API}/{_sheet_id()}/values/{range_}"
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json().get("values", [])


def _values_update(headers: dict[str, str], range_: str, values: list[list[str]]) -> None:
    url = f"{_SHEETS_API}/{_sheet_id()}/values/{range_}?valueInputOption=RAW"
    response = requests.put(url, headers=headers, json={"values": values}, timeout=20)
    response.raise_for_status()


def _values_append(headers: dict[str, str], range_: str, values: list[list[str]]) -> None:
    url = (
        f"{_SHEETS_API}/{_sheet_id()}/values/{range_}:append"
        "?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    )
    response = requests.post(url, headers=headers, json={"values": values}, timeout=20)
    response.raise_for_status()


def _ensure_header_row(headers: dict[str, str]) -> None:
    sheet = _sheet_name()
    existing = _values_get(headers, f"{sheet}!A1:{_LAST_COL}1")
    if not existing or not existing[0] or existing[0][0] != HEADERS[0]:
        _values_update(headers, f"{sheet}!A1:{_LAST_COL}1", [HEADERS])


def _find_row_by_contact_id(headers: dict[str, str], contact_id: str) -> int | None:
    """Return the 1-based sheet row holding this Contact ID, or None."""
    id_column = _values_get(headers, f"{_sheet_name()}!A:A")
    for index, row in enumerate(id_column, start=1):
        if row and row[0].strip() == contact_id:
            return index
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Sync entry points
# ─────────────────────────────────────────────────────────────────────────────

def _upsert_row(contact: dict[str, Any], extras: dict[str, Any] | None) -> None:
    auth = _auth_headers()
    if not auth:
        raise RuntimeError("Google Sheets auth failed (no access token).")

    sheet = _sheet_name()
    _ensure_header_row(auth)

    contact_id = str(contact.get("id") or "")
    row = contact_to_row(contact, extras)
    existing_row = _find_row_by_contact_id(auth, contact_id)
    if existing_row:
        _values_update(auth, f"{sheet}!A{existing_row}:{_LAST_COL}{existing_row}", [row])
        logger.info("Google Sheets: updated row %s for contact %s.", existing_row, contact_id)
    else:
        _values_append(auth, f"{sheet}!A:{_LAST_COL}", [row])
        logger.info("Google Sheets: appended row for contact %s.", contact_id)


def sync_contact_to_sheet(
    contact: dict[str, Any],
    extras: dict[str, Any] | None = None,
) -> bool:
    """Upsert one contact into the sheet. Returns True on success.

    Never raises — Sheets is a secondary layer and must not affect saves.
    """
    if not is_sheets_configured():
        logger.debug("Google Sheets sync skipped: not configured.")
        return False

    contact_id = str(contact.get("id") or "")
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            _upsert_row(contact, extras)
            with _pending_lock:
                _pending_retry.pop(contact_id, None)
            return True
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_DELAYS[min(attempt - 1, len(_RETRY_DELAYS) - 1)])

    logger.error(
        "Google Sheets sync failed for contact %s after %s attempts: %s "
        "(contact is safe in PostgreSQL; queued for retry on next sync).",
        contact_id,
        _MAX_ATTEMPTS,
        last_error,
    )
    with _pending_lock:
        _pending_retry[contact_id] = {"extras": extras or {}}
    return False


def sync_contact_by_id(contact_id: str, extras: dict[str, Any] | None = None) -> bool:
    """Fetch the committed contact from PostgreSQL and upsert it into the sheet."""
    if not is_sheets_configured():
        return False
    from services import contact_storage as storage

    contact = storage.get_contact(contact_id)
    if not contact:
        logger.warning("Google Sheets sync skipped: contact %s not found in PostgreSQL.", contact_id)
        return False

    ok = sync_contact_to_sheet(contact, extras)
    if ok:
        _drain_pending_retries(exclude_id=contact_id)
    return ok


def _drain_pending_retries(exclude_id: str | None = None) -> None:
    with _pending_lock:
        pending = {cid: meta for cid, meta in _pending_retry.items() if cid != exclude_id}
    if not pending:
        return
    from services import contact_storage as storage

    for cid, meta in pending.items():
        contact = storage.get_contact(cid)
        if contact:
            sync_contact_to_sheet(contact, meta.get("extras"))
        else:
            with _pending_lock:
                _pending_retry.pop(cid, None)


# Strong references so fire-and-forget tasks are not garbage-collected mid-run.
_background_tasks: set[asyncio.Task] = set()


def fire_sheets_sync(contact_id: str, extras: dict[str, Any] | None = None) -> None:
    """Fire-and-forget sheet sync after a successful PostgreSQL commit.

    Runs in a worker thread via asyncio so the API response is never blocked.
    """
    if not is_sheets_configured() or not contact_id:
        return

    async def _run() -> None:
        try:
            await asyncio.to_thread(sync_contact_by_id, contact_id, extras)
        except Exception as exc:
            logger.error("Google Sheets background sync crashed for %s: %s", contact_id, exc)

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(_run())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        # No running loop (sync context / tests) — run inline but still guarded.
        threading.Thread(
            target=sync_contact_by_id, args=(contact_id, extras), daemon=True
        ).start()
