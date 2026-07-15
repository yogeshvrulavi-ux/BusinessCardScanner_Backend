"""OTP-based password reset — sends OTP via production email, updates Neon Auth password."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import psycopg2
from psycopg2 import Error as PsycopgError
from psycopg2.extras import RealDictCursor

from services.auth_service import neon_auth_url
from services.email_service import is_email_configured, send_password_reset_otp_email

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
VERIFICATION_TTL_MINUTES = 15

_OTP_PEPPER = os.getenv("PASSWORD_RESET_OTP_PEPPER", "cardsync-password-reset")


class PasswordResetError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _postgres_url() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        return ""
    return raw.split("?", 1)[0]


def _connect():
    url = _postgres_url()
    if not url:
        raise PasswordResetError(
            "DATABASE_URL is not configured on the server.",
            status_code=503,
        )
    try:
        return psycopg2.connect(url)
    except PsycopgError as exc:
        logger.error("PostgreSQL connection failed: %s", exc)
        raise PasswordResetError(
            "Database connection failed. Check DATABASE_URL in backend/.env "
            "(use the full Neon connection string with your real password).",
            status_code=503,
        ) from exc


def _is_missing_neon_auth_schema(exc: PsycopgError) -> bool:
    message = str(exc).lower()
    return (
        "neon_auth" in message
        and ("does not exist" in message or "undefined" in message)
    ) or "undefinedtable" in message.replace(" ", "")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_otp(email: str, otp: str) -> str:
    payload = f"{_OTP_PEPPER}:{email.strip().lower()}:{otp}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _generate_otp() -> str:
    upper = 10**OTP_LENGTH
    return str(secrets.randbelow(upper)).zfill(OTP_LENGTH)


def ensure_otp_table() -> None:
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS password_reset_otps (
                      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                      email TEXT NOT NULL,
                      otp_hash TEXT NOT NULL,
                      expires_at TIMESTAMPTZ NOT NULL,
                      attempts INT NOT NULL DEFAULT 0,
                      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_password_reset_otps_email
                    ON password_reset_otps (lower(email))
                    """
                )
            conn.commit()
    except PasswordResetError:
        raise
    except PsycopgError as exc:
        logger.error("Could not create password_reset_otps table: %s", exc)
        raise PasswordResetError(
            "Database error while preparing password reset. Verify DATABASE_URL.",
            status_code=503,
        ) from exc


def _find_neon_user(email: str) -> dict[str, Any] | None:
    normalized = email.strip().lower()
    try:
        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, email
                    FROM neon_auth."user"
                    WHERE lower(email) = %s
                    LIMIT 1
                    """,
                    (normalized,),
                )
                row = cur.fetchone()
        return dict(row) if row else None
    except PasswordResetError:
        raise
    except PsycopgError as exc:
        if _is_missing_neon_auth_schema(exc):
            logger.warning("neon_auth schema not found — enable Neon Auth in Neon Console.")
            return None
        logger.error("Failed to look up Neon Auth user: %s", exc)
        raise PasswordResetError(
            "Database error while looking up account. Verify DATABASE_URL and Neon Auth.",
            status_code=503,
        ) from exc


def _latest_otp_row(email: str) -> dict[str, Any] | None:
    normalized = email.strip().lower()
    with _connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, email, otp_hash, expires_at, attempts, created_at
                FROM password_reset_otps
                WHERE lower(email) = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (normalized,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def _delete_otps_for_email(email: str) -> None:
    normalized = email.strip().lower()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM password_reset_otps WHERE lower(email) = %s",
                (normalized,),
            )
        conn.commit()


def _insert_otp(email: str, otp: str) -> None:
    normalized = email.strip().lower()
    expires_at = _utcnow() + timedelta(minutes=OTP_TTL_MINUTES)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM password_reset_otps WHERE lower(email) = %s",
                (normalized,),
            )
            cur.execute(
                """
                INSERT INTO password_reset_otps (email, otp_hash, expires_at)
                VALUES (%s, %s, %s)
                """,
                (normalized, _hash_otp(normalized, otp), expires_at),
            )
        conn.commit()


def send_password_reset_otp(email: str) -> dict[str, Any]:
    """Send a one-time code to the user's email."""
    if not is_email_configured():
        raise PasswordResetError(
            "Email is not configured on the server. Set GMAIL_USER + GMAIL_APP_PASSWORD (or SMTP_USER + SMTP_PASSWORD).",
            status_code=503,
        )

    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise PasswordResetError("Enter a valid email address.")

    ensure_otp_table()

    user = _find_neon_user(normalized)
    if not user:
        # Avoid email enumeration — same response shape, skip send.
        logger.info("Password reset requested for unknown email: %s", normalized)
        return {
            "ok": True,
            "message": "If an account exists for this email, a verification code has been sent.",
        }

    latest = _latest_otp_row(normalized)
    if latest:
        created = latest["created_at"]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        elapsed = (_utcnow() - created).total_seconds()
        if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
            wait = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
            raise PasswordResetError(
                f"Please wait {wait} seconds before requesting another code.",
                status_code=429,
            )

    otp = _generate_otp()
    delivery = send_password_reset_otp_email(normalized, otp)
    if not delivery.get("success"):
        raise PasswordResetError(
            delivery.get("error") or "Failed to send verification email.",
            status_code=503,
        )

    _insert_otp(normalized, otp)
    logger.info("Password reset OTP sent to %s", normalized)
    return {
        "ok": True,
        "message": "If an account exists for this email, a verification code has been sent.",
        "expiresInMinutes": OTP_TTL_MINUTES,
    }


async def _reset_via_neon_auth(email: str, new_password: str) -> None:
    base = neon_auth_url()
    if not base:
        raise PasswordResetError(
            "NEON_AUTH_URL is not configured on the server.",
            status_code=503,
        )

    token = str(uuid.uuid4())
    now = _utcnow()
    expires_at = now + timedelta(minutes=VERIFICATION_TTL_MINUTES)
    verification_id = str(uuid.uuid4())

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM neon_auth.verification
                WHERE lower(identifier) = %s
                """,
                (email.strip().lower(),),
            )
            cur.execute(
                """
                INSERT INTO neon_auth.verification
                  (id, identifier, value, "expiresAt", "createdAt", "updatedAt")
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    verification_id,
                    email.strip().lower(),
                    token,
                    expires_at,
                    now,
                    now,
                ),
            )
        conn.commit()

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{base}/reset-password",
            json={"newPassword": new_password, "token": token},
            headers={"Content-Type": "application/json"},
        )

    if response.status_code >= 400:
        logger.error(
            "Neon Auth reset-password failed (%s): %s",
            response.status_code,
            response.text,
        )
        raise PasswordResetError(
            "Could not update password. Please request a new code and try again.",
            status_code=502,
        )


def confirm_password_reset(
    email: str,
    otp: str,
    new_password: str,
    confirm_password: str,
) -> dict[str, Any]:
    """Verify OTP and set a new password in Neon Auth."""
    normalized = email.strip().lower()
    code = otp.strip()

    if not normalized or "@" not in normalized:
        raise PasswordResetError("Enter a valid email address.")
    if len(code) != OTP_LENGTH or not code.isdigit():
        raise PasswordResetError("Enter the 6-digit verification code.")
    if len(new_password) < 8:
        raise PasswordResetError("Password must be at least 8 characters.")
    if new_password != confirm_password:
        raise PasswordResetError("Passwords do not match.")

    ensure_otp_table()

    user = _find_neon_user(normalized)
    if not user:
        raise PasswordResetError("Invalid verification code or email.")

    row = _latest_otp_row(normalized)
    if not row:
        raise PasswordResetError("No verification code found. Request a new code.")

    expires_at = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if _utcnow() > expires_at:
        _delete_otps_for_email(normalized)
        raise PasswordResetError("Verification code expired. Request a new code.")

    attempts = int(row.get("attempts") or 0)
    if attempts >= OTP_MAX_ATTEMPTS:
        _delete_otps_for_email(normalized)
        raise PasswordResetError("Too many attempts. Request a new code.")

    if row["otp_hash"] != _hash_otp(normalized, code):
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE password_reset_otps
                    SET attempts = attempts + 1
                    WHERE id = %s
                    """,
                    (row["id"],),
                )
            conn.commit()
        raise PasswordResetError("Invalid verification code.")

    return {
        "ok": True,
        "email": normalized,
        "new_password": new_password,
    }


async def confirm_password_reset_async(
    email: str,
    otp: str,
    new_password: str,
    confirm_password: str,
) -> dict[str, Any]:
    pending = confirm_password_reset(email, otp, new_password, confirm_password)
    await _reset_via_neon_auth(pending["email"], pending["new_password"])
    _delete_otps_for_email(pending["email"])
    return {
        "ok": True,
        "message": "Password updated successfully. You can sign in with your new password.",
    }
