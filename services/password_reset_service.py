"""Legacy password-reset module — delegates to PostgreSQL RBAC auth.

Neon Auth has been removed. Prefer auth.service.forgot_password / reset_password.
"""

from __future__ import annotations

from auth.service import AuthError, forgot_password, reset_password


class PasswordResetError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def send_password_reset_otp(email: str) -> dict:
    try:
        return forgot_password(email)
    except AuthError as exc:
        raise PasswordResetError(exc.message, exc.status_code) from exc


async def confirm_password_reset_async(
    email: str,
    otp: str,
    password: str,
    confirm_password: str,
) -> dict:
    if password != confirm_password:
        raise PasswordResetError("Passwords do not match.", 400)
    try:
        return reset_password(email, otp, password)
    except AuthError as exc:
        raise PasswordResetError(exc.message, exc.status_code) from exc
