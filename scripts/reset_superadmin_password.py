#!/usr/bin/env python3
"""Reset SuperAdmin password from .env — does NOT touch schema or other data.

Reads:
  SUPERADMIN_EMAIL
  SUPERADMIN_PASSWORD

Usage (from BusinessCardScanner_Backend):
  python scripts/reset_superadmin_password.py

Then sign in with the new SUPERADMIN_PASSWORD from .env.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.env_loader import load_env  # noqa: E402

load_env()


def main() -> int:
    from auth.password_utils import hash_password, validate_password_policy
    from db.pool import close_pool, db_cursor, init_pool

    email = (os.getenv("SUPERADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("SUPERADMIN_PASSWORD") or ""

    if not email:
        print("SUPERADMIN_EMAIL is not set in .env", file=sys.stderr)
        return 1
    if not password:
        print("SUPERADMIN_PASSWORD is not set in .env", file=sys.stderr)
        return 1

    ok, errors = validate_password_policy(password)
    if not ok:
        print("Password does not meet policy:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    init_pool()
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT u.id, u.email, r.name AS role_name
                FROM users u
                JOIN roles r ON r.id = u.role_id
                WHERE lower(u.email) = %s AND u.deleted_at IS NULL
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row:
                print(f"No user found for SUPERADMIN_EMAIL={email}", file=sys.stderr)
                print("Seed creates SuperAdmin only once; check the email spelling.", file=sys.stderr)
                return 1

            role = (row.get("role_name") or "").upper()
            if role != "SUPER_ADMIN":
                print(
                    f"Refusing to reset: {email} has role {role!r}, not SUPER_ADMIN.",
                    file=sys.stderr,
                )
                return 1

            now = datetime.now(timezone.utc)
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s,
                    last_password_change = %s,
                    updated_at = %s,
                    failed_login_attempts = 0,
                    locked_until = NULL
                WHERE id = %s
                """,
                (hash_password(password), now, now, row["id"]),
            )

        # Best-effort: force re-login on other devices (safe if token tables missing)
        try:
            from auth import session_service, token_service

            token_service.revoke_all_for_user(row["id"])
            session_service.end_all_sessions(row["id"])
        except Exception as exc:  # noqa: BLE001
            print(f"Password updated; session revoke skipped: {exc}")

        print(f"SuperAdmin password updated for {email}")
        print("Schema and other data were not modified.")
        print("Sign in with SUPERADMIN_PASSWORD from .env.")
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
