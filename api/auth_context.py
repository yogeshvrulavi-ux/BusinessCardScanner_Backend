"""Resolve authenticated user from FastAPI request state (RBAC middleware)."""

from __future__ import annotations

from typing import Any

from fastapi import Request


def get_request_app_user(request: Request) -> dict[str, Any] | None:
    """Return the authenticated user dict attached by RBACMiddleware.

    Returns None if the request is unauthenticated (e.g. auth disabled or public route).
    """
    user = getattr(request.state, "auth_user", None)
    if not isinstance(user, dict):
        return None
    user_id = str(user.get("id") or "").strip()
    email = str(user.get("email") or "").strip().lower()
    if not user_id and not email:
        return None
    return {
        "id": user_id,
        "email": email,
        "role": user.get("role", ""),
        "company_id": user.get("company_id"),
        "admin_id": user.get("admin_id"),
    }


def app_user_filter_kwargs(request: Request) -> dict[str, str | None]:
    """Keyword args for scoped contact queries — email/id of the authenticated user."""
    user = get_request_app_user(request)
    if not user:
        return {"filter_user_email": None, "filter_user_id": None}

    email = str(user.get("email") or "").strip().lower() or None
    user_id = str(user.get("id") or "").strip() or None
    return {"filter_user_email": email, "filter_user_id": user_id}


def get_request_app_user_for_sync(request: Request) -> dict[str, Any] | None:
    """Authenticated user stamped onto contacts on create/sync."""
    return get_request_app_user(request)


def get_scanner_email_from_request(request: Request) -> str | None:
    """Logged-in CardSync user email — CC on thank-you emails (Owner)."""
    user = get_request_app_user(request)
    if not user:
        return None
    email = str(user.get("email") or "").strip().lower()
    return email or None
