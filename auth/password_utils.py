"""Password hashing (bcrypt) and policy validation."""

from __future__ import annotations

import re

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt with 12 salt rounds."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the bcrypt *hashed* value."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def validate_password_policy(password: str) -> tuple[bool, list[str]]:
    """Enforce enterprise password policy.

    Returns (is_valid, list_of_error_messages).
    """
    errors: list[str] = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", password):
        errors.append("Password must contain at least one special character.")

    return (len(errors) == 0, errors)
