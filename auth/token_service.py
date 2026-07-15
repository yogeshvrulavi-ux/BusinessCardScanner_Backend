"""Refresh-token persistence — SHA-256 hashed storage with rotation support."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from auth.constants import JWT_REFRESH_TOKEN_EXPIRE_DAYS
from db.pool import db_cursor

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    """SHA-256 hash the raw refresh token for safe storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def store_refresh_token(
    user_id: str,
    token: str,
    *,
    device: str = "",
    browser: str = "",
    ip: str = "",
    expires_days: int | None = None,
) -> str:
    """Hash and store a refresh token. Returns the token row id (UUID string)."""
    token_hash = _hash_token(token)
    token_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=expires_days or JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO refresh_tokens (id, user_id, token_hash, device, browser, ip, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (token_id, user_id, token_hash, device, browser, ip, expires_at),
        )
    return token_id


def find_refresh_token(token: str) -> dict[str, Any] | None:
    """Look up a refresh token by its raw value. Returns the row or None if expired/revoked."""
    token_hash = _hash_token(token)
    with db_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, user_id, token_hash, device, browser, ip, expires_at, created_at, revoked_at
            FROM refresh_tokens
            WHERE token_hash = %s
            """,
            (token_hash,),
        )
        row = cur.fetchone()

    if not row:
        return None

    row = dict(row)
    # Check revoked
    if row.get("revoked_at") is not None:
        return None
    # Check expired
    expires_at = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    return row


def revoke_refresh_token(token_id: str) -> None:
    """Mark a refresh token as revoked."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE refresh_tokens SET revoked_at = %s WHERE id = %s",
            (datetime.now(timezone.utc), token_id),
        )


def revoke_token_by_raw(token: str) -> None:
    """Revoke a refresh token by its raw value."""
    token_hash = _hash_token(token)
    with db_cursor() as cur:
        cur.execute(
            "UPDATE refresh_tokens SET revoked_at = %s WHERE token_hash = %s",
            (datetime.now(timezone.utc), token_hash),
        )


def revoke_all_for_user(user_id: str) -> int:
    """Revoke all refresh tokens for a given user. Returns count revoked."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE refresh_tokens SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL",
            (datetime.now(timezone.utc), user_id),
        )
        return cur.rowcount


def cleanup_expired_tokens() -> int:
    """Delete expired and revoked tokens older than 30 days. Returns count deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    with db_cursor() as cur:
        cur.execute(
            """
            DELETE FROM refresh_tokens
            WHERE revoked_at IS NOT NULL
              AND revoked_at < %s
            """,
            (cutoff,),
        )
        return cur.rowcount
