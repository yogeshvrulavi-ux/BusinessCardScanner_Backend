"""Resolve Neon Auth user from FastAPI request state."""

from __future__ import annotations

from fastapi import Request

from services.auth_service import is_auth_enabled


def get_request_app_user(request: Request) -> dict | None:
    user = getattr(request.state, "auth_user", None)
    if not isinstance(user, dict):
        return None
    user_id = str(user.get("id") or user.get("sub") or "").strip()
    email = str(user.get("email") or "").strip().lower()
    if not user_id and not email:
        return None
    return {"id": user_id, "email": email}


def app_user_filter_kwargs(request: Request) -> dict[str, str | None]:
    """Keyword args for get_leads() — no filter when auth is disabled."""
    if not is_auth_enabled():
        return {"filter_user_email": None, "filter_user_id": None}

    user = get_request_app_user(request)
    if not user:
        return {"filter_user_email": None, "filter_user_id": None}

    email = str(user.get("email") or "").strip().lower() or None
    user_id = str(user.get("id") or "").strip() or None
    return {"filter_user_email": email, "filter_user_id": user_id}


def get_request_app_user_for_sync(request: Request) -> dict | None:
    """App user stamped onto Zoho leads on create/sync (when auth is enabled)."""
    if not is_auth_enabled():
        return None
    return get_request_app_user(request)


def get_scanner_email_from_request(request: Request) -> str | None:
    """Logged-in CardSync user email — CC on thank-you emails (Owner)."""
    user = get_request_app_user(request)
    if not user:
        return None
    email = str(user.get("email") or "").strip().lower()
    return email or None
