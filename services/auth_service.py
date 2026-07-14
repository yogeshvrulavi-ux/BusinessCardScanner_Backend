"""Neon Auth session verification for FastAPI."""

from __future__ import annotations

import asyncio
import logging
import os
from functools import lru_cache
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_PUBLIC_PREFIXES = (
    "/health",
    "/webhook",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/password-reset",
    "/static",
)


def neon_auth_url() -> str:
    return os.getenv("NEON_AUTH_URL", "").strip().rstrip("/")


def is_auth_enabled() -> bool:
    return bool(neon_auth_url())


def is_public_path(path: str) -> bool:
    if path in {"/", ""}:
        return True
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in _PUBLIC_PREFIXES)


@lru_cache(maxsize=1)
def _jwks_client():
    from jwt import PyJWKClient

    base = neon_auth_url()
    return PyJWKClient(f"{base}/.well-known/jwks.json", cache_keys=True)


def _verify_neon_jwt(token: str) -> dict[str, Any] | None:
    """Validate JWT from authClient.token() (EdDSA via JWKS)."""
    from jwt import decode as jwt_decode

    base = neon_auth_url()
    if not base or not token or token.count(".") != 2:
        return None

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        payload = jwt_decode(
            token,
            signing_key.key,
            algorithms=["EdDSA", "ES256", "RS256", "HS256"],
            options={"verify_aud": False},
        )
    except Exception as exc:
        logger.debug("Neon Auth JWT verification failed: %s", exc)
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    return {
        "user": {
            "id": str(user_id),
            "email": str(payload.get("email") or ""),
        },
        "session": {"token": token},
    }


async def _verify_session_token(token: str) -> dict[str, Any] | None:
    """Validate opaque session token via Neon Auth get-session."""
    base = neon_auth_url()
    if not base or not token:
        return None

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base}/get-session", headers=headers)
            if response.status_code != 200:
                return None
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Neon Auth session verification failed: %s", exc)
        return None

    user = payload.get("user") if isinstance(payload, dict) else None
    session = payload.get("session") if isinstance(payload, dict) else None
    if not user or not session:
        return None

    return {
        "user": user,
        "session": session,
    }


async def verify_neon_session(token: str) -> dict[str, Any] | None:
    """Validate bearer token — JWT (preferred) or opaque session token."""
    if not token:
        return None

    jwt_payload = await asyncio.to_thread(_verify_neon_jwt, token)
    if jwt_payload:
        user = jwt_payload.get("user") or {}
        if not str(user.get("email") or "").strip():
            session_payload = await _verify_session_token(token)
            if session_payload:
                session_user = session_payload.get("user") or {}
                if str(session_user.get("email") or "").strip():
                    user = {**user, "email": session_user.get("email")}
                    jwt_payload = {**jwt_payload, "user": user}
        return jwt_payload

    return await _verify_session_token(token)
