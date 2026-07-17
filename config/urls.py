"""URL helpers — all public base URLs come from environment variables."""

from __future__ import annotations

import os


def _normalize_base(url: str) -> str:
    return url.strip().strip('"').strip("'").rstrip("/")


def get_frontend_base_url() -> str:
    """
    Public frontend origin for invitation / verify / reset links.

    Prefers FRONTEND_BASE_URL, then FRONTEND_URL (legacy alias).
    Raises if unset or still pointing at Netlify.
    """
    raw = os.getenv("FRONTEND_BASE_URL") or os.getenv("FRONTEND_URL") or ""
    base = _normalize_base(raw)
    if not base:
        raise RuntimeError(
            "FRONTEND_BASE_URL is not set. "
            "Add it to BusinessCardScanner_Backend/.env "
            "(e.g. https://your-amplify-domain or http://localhost:5173 for local)."
        )
    if "netlify.app" in base.lower() or "netlify.com" in base.lower():
        raise RuntimeError(
            f"FRONTEND_BASE_URL still points at Netlify ({base}). "
            "Set FRONTEND_BASE_URL to your AWS Amplify custom domain."
        )
    return base


def get_backend_base_url() -> str:
    """
    Public backend origin for PDF links, webhooks docs, etc.

    Prefers BACKEND_BASE_URL, then PUBLIC_API_URL, then API_BASE_URL.
    """
    raw = (
        os.getenv("BACKEND_BASE_URL")
        or os.getenv("PUBLIC_API_URL")
        or os.getenv("API_BASE_URL")
        or ""
    )
    base = _normalize_base(raw)
    if not base:
        raise RuntimeError(
            "BACKEND_BASE_URL is not set. "
            "Add it to BusinessCardScanner_Backend/.env "
            "(e.g. https://api.example.com or http://127.0.0.1:5000 for local)."
        )
    if "netlify.app" in base.lower():
        raise RuntimeError(
            f"BACKEND_BASE_URL must not use Netlify ({base})."
        )
    return base


def try_frontend_base_url() -> str | None:
    """Like get_frontend_base_url but returns None instead of raising."""
    try:
        return get_frontend_base_url()
    except RuntimeError:
        return None


def try_backend_base_url() -> str | None:
    try:
        return get_backend_base_url()
    except RuntimeError:
        return None
