"""JWT token creation and verification utilities."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from auth.constants import (
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    JWT_SECRET_KEY,
)

logger = logging.getLogger(__name__)


def create_access_token(
    user_id: str,
    role: str,
    company_id: str | None = None,
    *,
    session_id: str,
    extra_claims: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    """Create a short-lived JWT access token. session_id is required for session binding."""
    if not session_id:
        raise ValueError("session_id is required on access tokens.")

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_minutes or JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "session_id": session_id,
        "iat": now,
        "exp": exp,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    if company_id:
        payload["company_id"] = company_id
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    user_id: str,
    session_id: str,
    *,
    expires_days: int | None = None,
) -> str:
    """Create a long-lived JWT refresh token. session_id is always required."""
    if not session_id:
        raise ValueError("session_id is required on refresh tokens.")

    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=expires_days or JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    payload: dict[str, Any] = {
        "sub": user_id,
        "session_id": session_id,
        "iat": now,
        "exp": exp,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT (access or refresh). Returns payload dict or None."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired.")
        return None
    except jwt.InvalidIssuerError:
        logger.debug("JWT invalid issuer.")
        return None
    except jwt.InvalidAudienceError:
        logger.debug("JWT invalid audience.")
        return None
    except jwt.PyJWTError as exc:
        logger.debug("JWT decode error: %s", exc)
        return None


def verify_access_token(token: str) -> dict[str, Any] | None:
    """Verify an access token. Returns payload or None."""
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") != "access":
        return None
    return payload


def verify_refresh_token(token: str) -> dict[str, Any] | None:
    """Verify a refresh token. Returns payload or None."""
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") != "refresh":
        return None
    return payload


def token_expiry_days() -> int:
    return JWT_REFRESH_TOKEN_EXPIRE_DAYS


def token_expiry_minutes() -> int:
    return JWT_ACCESS_TOKEN_EXPIRE_MINUTES
