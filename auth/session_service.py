"""Session management — tracks active sessions per user with device info."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from auth.constants import SESSION_ABSOLUTE_TIMEOUT_HOURS, SESSION_TIMEOUT_MINUTES
from db.pool import db_cursor

logger = logging.getLogger(__name__)


def create_session(
    user_id: str,
    refresh_token_id: str,
    *,
    session_id: str | None = None,
    device: str = "",
    browser: str = "",
    ip: str = "",
    expires_hours: int | None = None,
) -> str:
    """Insert a new session row. Returns the session id (UUID).

    Pass an explicit session_id when the refresh JWT was already minted with that id.
    """
    sid = session_id or str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=expires_hours or SESSION_ABSOLUTE_TIMEOUT_HOURS
    )

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO sessions (id, user_id, refresh_token_id, device, browser, ip, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (sid, user_id, refresh_token_id, device, browser, ip, expires_at),
        )
    return sid


def update_activity(session_id: str) -> None:
    """Bump last_activity to now (called on every token refresh / protected request)."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET last_activity = %s WHERE id = %s AND status = 'active'",
            (datetime.now(timezone.utc), session_id),
        )


def validate_session(session_id: str, user_id: str, *, touch: bool = True) -> bool:
    """Return True when the session is active, owned by user_id, and within timeouts.

    Ends the session when idle or absolute timeout is exceeded.
    """
    if not session_id or not user_id:
        return False

    now = datetime.now(timezone.utc)
    with db_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, user_id, status, last_activity, expires_at
            FROM sessions
            WHERE id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()

    if not row:
        return False

    row = dict(row)
    if str(row.get("user_id")) != str(user_id):
        return False
    if row.get("status") != "active":
        return False

    expires_at = row.get("expires_at")
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            _end_session(session_id)
            return False

    last_activity = row.get("last_activity")
    if last_activity is not None:
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        if (now - last_activity) > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
            _end_session(session_id)
            return False

    if touch:
        update_activity(session_id)
    return True


def get_active_sessions(user_id: str) -> list[dict[str, Any]]:
    """Return all active, non-expired sessions for a user."""
    now = datetime.now(timezone.utc)
    with db_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, device, browser, ip, login_at, last_activity, status, expires_at
            FROM sessions
            WHERE user_id = %s AND status = 'active' AND expires_at > %s
            ORDER BY last_activity DESC
            """,
            (user_id, now),
        )
        rows = cur.fetchall()

    results = []
    for row in rows:
        row = dict(row)
        # Check inactivity timeout
        last_activity = row.get("last_activity")
        if last_activity:
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            if (now - last_activity) > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                # Mark expired
                _end_session(row["id"])
                continue
        # Serialize datetimes
        for key in ("login_at", "last_activity", "expires_at"):
            if row.get(key) and hasattr(row[key], "isoformat"):
                row[key] = row[key].isoformat()
        results.append(row)
    return results


def end_session(session_id: str) -> None:
    """Mark a single session as ended."""
    _end_session(session_id)


def _end_session(session_id: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET status = 'ended' WHERE id = %s",
            (session_id,),
        )


def end_all_sessions(user_id: str) -> int:
    """Mark all active sessions for a user as ended. Returns count."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET status = 'ended' WHERE user_id = %s AND status = 'active'",
            (user_id,),
        )
        return cur.rowcount


def get_session(session_id: str) -> dict[str, Any] | None:
    """Return a single session row or None."""
    with db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM sessions WHERE id = %s",
            (session_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    row = dict(row)
    if row.get("login_at") and hasattr(row["login_at"], "isoformat"):
        row["login_at"] = row["login_at"].isoformat()
    if row.get("last_activity") and hasattr(row["last_activity"], "isoformat"):
        row["last_activity"] = row["last_activity"].isoformat()
    if row.get("expires_at") and hasattr(row["expires_at"], "isoformat"):
        row["expires_at"] = row["expires_at"].isoformat()
    return row


def cleanup_expired_sessions() -> int:
    """Delete sessions that have been ended or expired for more than 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM sessions WHERE status = 'ended' OR expires_at < %s",
            (cutoff,),
        )
        return cur.rowcount
